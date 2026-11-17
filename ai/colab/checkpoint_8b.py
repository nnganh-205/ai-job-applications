"""Portable, verified Trainer checkpoints. No cloud credentials or model imports."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import uuid
import zipfile

FORMAT = 1
REQUIRED = {
    'adapter_config.json', 'adapter_model.safetensors', 'trainer_state.json',
    'training_args.bin', 'optimizer.pt', 'scheduler.pt', 'rng_state.pth',
}


def required_files(identity):
    # BF16 has no GradScaler. FP16 resume must preserve the scaler as well.
    return REQUIRED | ({'scaler.pt'} if identity['config']['precision'] == 'float16' else set())


def slot_name(step, identity):
    # Step 1 and step 25 must occupy different slots, too.
    return f"checkpoint-slot-{(step // identity['config']['save_steps']) % 3}.zip"


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def identity_hash(identity):
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.partial')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def require_drive(root):
    """Never mistake a local directory for persistent Google Drive storage."""
    root = Path(root)
    mount = Path('/content/drive')
    if not os.path.ismount(mount) or not root.is_relative_to(mount / 'MyDrive'):
        raise RuntimeError('Mount Google Drive tại /content/drive trước khi train. Không lưu backup vào /content tạm.')
    root.mkdir(parents=True, exist_ok=True)
    probe = root / ('.write-test-' + uuid.uuid4().hex)
    try:
        probe.write_bytes(b'checkpoint-write-test')
        if probe.read_bytes() != b'checkpoint-write-test':
            raise OSError('Drive write/read verification failed')
    finally:
        probe.unlink(missing_ok=True)
    return root


def _checkpoint_step(folder, identity):
    folder = Path(folder)
    names = {p.name for p in folder.iterdir() if p.is_file() and p.stat().st_size}
    required = required_files(identity)
    if required - names:
        raise ValueError('Checkpoint chưa đầy đủ: ' + ', '.join(sorted(required - names)))
    state = json.loads((folder / 'trainer_state.json').read_text())
    step = state.get('global_step')
    if not isinstance(step, int) or step < 1 or state.get('max_steps', 0) < step:
        raise ValueError('Trainer state không hợp lệ')
    if folder.name != f'checkpoint-{step}':
        raise ValueError('Tên checkpoint không khớp global_step')
    return step


def _safe_name(name):
    path = PurePosixPath(name)
    return (not path.is_absolute() and '..' not in path.parts and '\\' not in name
            and bool(path.parts) and path.parts[0] in {'checkpoint', 'context', 'transfer.json'})


def inspect_archive(archive, identity):
    """Verify every byte before extracting any checkpoint or consuming torch state."""
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or any(not _safe_name(n) for n in names):
            raise ValueError('ZIP có đường dẫn không hợp lệ hoặc trùng lặp')
        metadata = json.loads(z.read('transfer.json'))
        if metadata.get('format') != FORMAT or metadata.get('identity') != identity:
            raise ValueError('Checkpoint khác model, dữ liệu, mã train hoặc cấu hình môi trường')
        entries = metadata.get('files', {})
        if set(names) != set(entries) | {'transfer.json'}:
            raise ValueError('Danh sách tệp trong checkpoint không khớp manifest')
        if {f'checkpoint/{n}' for n in required_files(identity)} - set(entries):
            raise ValueError('ZIP thiếu trạng thái optimizer/scheduler/RNG/scaler hoặc adapter')
        for name, expected in entries.items():
            value = hashlib.sha256()
            with z.open(name) as stream:
                for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                    value.update(chunk)
            if value.hexdigest() != expected:
                raise ValueError('Checksum sai: ' + name)
        state = json.loads(z.read('checkpoint/trainer_state.json'))
        if state.get('global_step') != metadata.get('step') or state.get('max_steps', 0) < state['global_step']:
            raise ValueError('Global step trong ZIP không khớp')
        return metadata


def backup_checkpoint(work, folder, persistent, identity):
    work, folder, persistent = Path(work), Path(folder), Path(persistent)
    step = _checkpoint_step(folder, identity)
    persistent.mkdir(parents=True, exist_ok=True)
    local = work / 'run-8b-unsloth' / 'transfers'
    local.mkdir(parents=True, exist_ok=True)
    archive = local / 'checkpoint-transfer.zip'
    temporary = archive.with_suffix('.partial')
    context = [work / 'ai/data/processed/cv8b-v1', work / 'ai/colab']
    extra = ['base-generation.json', 'generation-eval-inputs.json', 'environment.json',
             'tokenization-audit.json', 'run-8b-unsloth/run-identity.json',
             'run-8b-unsloth/progress.jsonl']
    files = {f'checkpoint/{p.relative_to(folder).as_posix()}': p for p in folder.rglob('*') if p.is_file()}
    for root in context:
        if root.exists():
            for p in root.rglob('*'):
                if p.is_file() and p.suffix in {'.py', '.json', '.jsonl', '.txt'}:
                    files['context/' + p.relative_to(work).as_posix()] = p
    for name in extra:
        if (work / name).is_file():
            files['context/' + name] = work / name
    if any(p.is_symlink() for p in files.values()):
        raise ValueError('Không đưa symlink vào checkpoint')
    metadata = dict(format=FORMAT, identity=identity, step=step,
                    files={name: sha256(path) for name, path in files.items()})
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as z:
            for name, path in files.items():
                z.write(path, name)
            z.writestr('transfer.json', json.dumps(metadata, ensure_ascii=False))
        inspect_archive(temporary, identity)
        temporary.replace(archive)
        # Three rotating files bound Drive usage while retaining two older copies.
        # The slot being replaced is never the only valid backup.
        copied = publish_file(archive, persistent / slot_name(step, identity))
        atomic_json(persistent / 'latest.json', dict(file=copied.name, sha256=sha256(copied), step=step))
        return copied
    finally:
        temporary.unlink(missing_ok=True)


def publish_file(source, destination):
    """Only publish the completion marker after a verified persistent copy exists."""
    source, destination = Path(source), Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pending = destination.with_name('.' + destination.name + '.' + uuid.uuid4().hex + '.partial')
    digest = sha256(source)
    try:
        shutil.copyfile(source, pending)
        if sha256(pending) != digest:
            raise OSError('Persistent backup checksum mismatch')
        pending.replace(destination)
        atomic_json(destination.with_suffix(destination.suffix + '.sha256.json'), {'sha256': digest})
        return destination
    finally:
        pending.unlink(missing_ok=True)


def restore_checkpoint(work, persistent, identity, mode, resume_zip=None):
    work, persistent = Path(work), Path(persistent)
    if mode not in {'new', 'resume'}:
        raise ValueError('START_MODE phải là new hoặc resume')
    archives = sorted(persistent.glob('checkpoint-*.zip'), reverse=True)
    local = work / 'run-8b-unsloth/checkpoints'
    if mode == 'new':
        if resume_zip or archives or (local.exists() and any(local.iterdir())):
            raise RuntimeError('Đã có checkpoint. Đặt START_MODE="resume" để tiếp tục, không ghi đè lượt cũ.')
        return None
    source = Path(resume_zip) if resume_zip else None
    metadata = None
    errors = []
    if source is not None:
        metadata = inspect_archive(source, identity)
    else:
        valid = []
        for candidate in archives:
            marker = candidate.with_suffix(candidate.suffix + '.sha256.json')
            try:
                if not marker.is_file() or sha256(candidate) != json.loads(marker.read_text())['sha256']:
                    raise ValueError('Backup chưa commit hoặc hỏng checksum')
                item = inspect_archive(candidate, identity)
                valid.append((item['step'], candidate, item))
            except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
                errors.append(f'{candidate.name}: {error}')
        if valid:
            _, source, metadata = max(valid, key=lambda item: item[0])
    if source is None:
        raise RuntimeError('Không có checkpoint hợp lệ để resume. ' + '; '.join(errors))
    local.mkdir(parents=True, exist_ok=True)
    destination = local / f'checkpoint-{metadata["step"]}'
    # Extract into a staging directory; a half-extracted checkpoint is never used.
    with tempfile.TemporaryDirectory(prefix='restore-', dir=local) as temporary:
        staged = Path(temporary) / destination.name
        staged.mkdir()
        with zipfile.ZipFile(source) as z:
            for name in metadata['files']:
                if name.startswith('checkpoint/'):
                    target = staged / PurePosixPath(name).relative_to('checkpoint')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(name) as src, target.open('wb') as out:
                        shutil.copyfileobj(src, out)
            _checkpoint_step(staged, identity)
            # Use the original pre-training baseline; never replace it with adapter output.
            for name in ['base-generation.json', 'generation-eval-inputs.json']:
                member = 'context/' + name
                if member not in metadata['files']:
                    raise ValueError('Checkpoint thiếu baseline/eval inputs để so sánh công bằng')
                data = z.read(member)
                if name == 'generation-eval-inputs.json' and (work / name).is_file() and (work / name).read_bytes() != data:
                    raise ValueError('Bộ câu đánh giá đã thay đổi')
                (work / name).write_bytes(data)
        if destination.exists():
            for p in staged.rglob('*'):
                if p.is_file() and (not (destination / p.relative_to(staged)).is_file() or sha256(p) != sha256(destination / p.relative_to(staged))):
                    raise ValueError('Checkpoint cục bộ khác bản backup; dùng runtime sạch')
        else:
            staged.replace(destination)
    # An archive imported from a different environment is backed up to this Drive too.
    if source.resolve() != (persistent / source.name).resolve():
        copied = publish_file(source, persistent / slot_name(metadata['step'], identity))
        atomic_json(persistent / 'latest.json', dict(file=copied.name, sha256=sha256(copied), step=metadata['step']))
    print(f'Restored optimizer step {metadata["step"]} from verified backup.', flush=True)
    return str(destination)

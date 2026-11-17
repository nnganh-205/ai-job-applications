import io
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,PngImagePlugin
from backend.tests import test_profile_drafts
from backend.app.services import assets


class PhotoTests(unittest.TestCase):
    setUp=test_profile_drafts.ProfileDraftTests.setUp

    def photo(self):
        out=io.BytesIO();meta=PngImagePlugin.PngInfo();meta.add_text('private_note','PRIVATE METADATA')
        Image.new('RGB',(800,1000),'#aaccee').save(out,format='PNG',pnginfo=meta)
        return out.getvalue()

    def test_photo_is_resized_reencoded_and_private(self):
        with patch.dict(os.environ,{'KLTN_ASSET_STORAGE':str(Path(self.tmp.name)/'assets')}):
            meta=assets.save_photo(self.photo());data=assets.read_photo(meta['asset_id'])
            self.assertNotIn(b'PRIVATE METADATA',data)
            with Image.open(io.BytesIO(data)) as image:
                self.assertLessEqual(image.width,640);self.assertLessEqual(image.height,800)
                self.assertFalse(image.getexif());self.assertEqual(image.format,'PNG')
            self.assertEqual(assets.save_photo(self.photo())['asset_id'],meta['asset_id'])

    def test_html_svg_and_path_inputs_are_rejected(self):
        for data in [b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',b'<html>image</html>']:
            with self.assertRaises(ValueError):assets.save_photo(data)
        with self.assertRaises(ValueError):assets.read_photo('../../secret')

    def test_tampered_blob_is_not_used(self):
        with patch.dict(os.environ,{'KLTN_ASSET_STORAGE':str(Path(self.tmp.name)/'assets')}):
            meta=assets.save_photo(self.photo());path=assets.storage()/(meta['asset_id']+'.png');path.write_bytes(path.read_bytes()+b'bad')
            with self.assertRaises(ValueError):assets.read_photo(meta['asset_id'])

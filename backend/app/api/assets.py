from typing import Annotated
from fastapi import APIRouter,UploadFile,File,HTTPException,Path
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from backend.app.services import assets

router=APIRouter(prefix='/api/assets',tags=['Private photos'])


@router.post('/photos')
async def upload(file:UploadFile=File(...)):
    try:
        content=await file.read(assets.MAX_UPLOAD+1)
        if len(content)>assets.MAX_UPLOAD:raise HTTPException(413,'Ảnh vượt 5 MB')
        return await run_in_threadpool(assets.save_photo,content)
    except ValueError as error:raise HTTPException(422,str(error)) from error
    finally:await file.close()


@router.get('/{asset_id}')
def read(asset_id:Annotated[str,Path(pattern=r'^asset_[a-f0-9]{64}$')]):
    try:content=assets.read_photo(asset_id)
    except LookupError as error:raise HTTPException(404,str(error)) from error
    except ValueError as error:raise HTTPException(422,str(error)) from error
    return Response(content,media_type='image/png',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

"""
Folder CRUD API endpoints
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Folder, Assessment
from schemas.folder import (
    FolderCreate,
    FolderUpdate,
    FolderResponse,
    FolderWithCount
)

router = APIRouter(prefix="/folders", tags=["folders"])


@router.get("", response_model=List[FolderWithCount])
async def list_folders(db: Session = Depends(get_db)):
    """Get all folders with assessment counts"""
    rows = (
        db.query(Folder, func.count(Assessment.id))
        .outerjoin(Assessment, Assessment.folder_id == Folder.id)
        .group_by(Folder.id)
        .all()
    )

    return [
        FolderWithCount(
            **FolderResponse.model_validate(folder).model_dump(),
            assessment_count=count,
        )
        for folder, count in rows
    ]


@router.get("/{folder_id}", response_model=FolderResponse)
async def get_folder(
    folder_id: int,
    db: Session = Depends(get_db)
):
    """Get a single folder by ID"""
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folder with id {folder_id} not found"
        )
    return folder


@router.post("", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    folder: FolderCreate,
    db: Session = Depends(get_db)
):
    """Create a new folder"""
    # Check if name already exists
    existing = db.query(Folder).filter(Folder.name == folder.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Folder with name '{folder.name}' already exists"
        )

    new_folder = Folder(**folder.model_dump())
    db.add(new_folder)
    db.commit()
    db.refresh(new_folder)
    return new_folder


@router.put("/{folder_id}", response_model=FolderResponse)
async def update_folder(
    folder_id: int,
    folder_update: FolderUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing folder"""
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folder with id {folder_id} not found"
        )

    # Update fields
    update_data = folder_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(folder, field, value)

    db.commit()
    db.refresh(folder)
    return folder


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: int,
    db: Session = Depends(get_db)
):
    """Delete a folder"""
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folder with id {folder_id} not found"
        )

    # Move assessments to no folder (folder_id = None)
    db.query(Assessment).filter(Assessment.folder_id == folder_id).update(
        {"folder_id": None}
    )

    db.delete(folder)
    db.commit()
    return None








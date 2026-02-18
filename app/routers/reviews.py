from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.categories import Category as CategoryModel
from app.models.products import Product as ProductModel
from app.models.reviews import Review as ReviewModel
from app.schemas import Review as ReviewSchema, ReviewCreate
from app.models.users import User as UserModel
from app.auth import get_current_buyer, get_current_user

from app.db_depends import get_async_db


router = APIRouter(
    prefix="/reviews",
    tags=["reviews"],
)


@router.get("/", response_model=list[ReviewSchema])
async def get_all_reviews(db: AsyncSession = Depends(get_async_db)):
    """
    Возвращает список всех отзывов.
    """
    stmt = await db.scalars(select(ReviewModel).where(ReviewModel.is_active == True))
    reviews = stmt.all()
    return reviews


@router.get("/products/{product_id}/", response_model=list[ReviewSchema])
async def get_all_reviews_of_product(product_id: int, db: AsyncSession = Depends(get_async_db)):
    """
    Возвращает список отзывов указанного товара.
    """
    product = await db.scalars(select(ProductModel).where(ProductModel.id == product_id,
                                                          ProductModel.is_active == True))
    if product.first() is None:
        raise HTTPException(status_code=404, detail="Product not found or inactive")
    stmt = await db.scalars(select(ReviewModel).where(ReviewModel.product_id == product_id,
                                                      ReviewModel.is_active == True))
    reviews_of_product = stmt.all()
    return reviews_of_product


@router.post("/", response_model=ReviewSchema, status_code=status.HTTP_201_CREATED)
async def create_review(comment: ReviewCreate, 
                        db: AsyncSession = Depends(get_async_db),
                        current_user: UserModel = Depends(get_current_buyer)):
    """
    Создаёт отзыв, привязанный к указанному товару.
    """
    stmt = await db.scalars(select(ProductModel).where(ProductModel.id == comment.product_id,
                                                       ProductModel.is_active == True))
    product = stmt.first()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found or inactive")
    
    
    db_review = ReviewModel(**comment.model_dump(), user_id=current_user.id)
    db.add(db_review)


    result = await db.execute(
        select(func.avg(ReviewModel.grade)).where(
            ReviewModel.product_id == comment.product_id,
            ReviewModel.is_active == True
        )
    )
    avg_rating = result.scalar() or 0.0
    product = await db.get(ProductModel, comment.product_id)
    product.rating = avg_rating
    await db.commit()
    await db.refresh(db_review)
    return db_review


@router.delete("/{review_id}", status_code=status.HTTP_200_OK)
async def delete_review(review_id: int,
                        db: AsyncSession = Depends(get_async_db),
                        current_user: UserModel = Depends(get_current_user)):
    """
    Выполняет мягкое удаление отзыва.
    """
    stmt = await db.scalars(select(ReviewModel).where(ReviewModel.id == review_id,
                                     ReviewModel.is_active == True))
    review = stmt.first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found or inactive")

    if review.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="User is not admin or author")
    
    review.is_active = False
    
    result = await db.execute(
        select(func.avg(ReviewModel.grade)).where(
            ReviewModel.product_id == review.product_id,
            ReviewModel.is_active == True
        )
    )
    avg_rating = result.scalar() or 0.0
    product = await db.get(ProductModel, review.product_id)
    product.rating = avg_rating
    await db.commit()
    await db.refresh(review)
    return {"Message": "Review deleted"}
    
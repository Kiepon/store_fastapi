from typing import Any
from decimal import Decimal # Точная работа с деньгами
from uuid import uuid4 # Для уникального idempotence_key (предотвращает дубли платежей)

from anyio import to_thread # Для запуска синхронного кода в async
from yookassa import Configuration, Payment

from app.config import (
    YOOKASSA_RETURN_URL,
    YOOKASSA_SECRET_KEY,
    YOOKASSA_SHOP_ID,
)


async def create_yookassa_payment(
    *, # Только именованные аргументы
    order_id: int, # ID заказа из БД
    amount: Decimal, # Сумма (для точности используется Decimal)
    user_email: str, # Email для чека
    description: str # Описание (пример: "Оплата заказа №1")
    ) -> dict[str, Any]: # Возврат в виде словаря (json)
    
    # Проверка настроек (fallback на ошибку)
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        raise RuntimeError("Задайте YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY в .env")
    
    # Глобальная настройка SDK (Basic Auth под капотом)
    Configuration.account_id = YOOKASSA_SHOP_ID
    Configuration.secret_key = YOOKASSA_SECRET_KEY
    
    
    # Формирование Payload - это главная часть.
    # Это JSON для POST-запроса /v3/payments.
    payload = {
        "amount": { # Сумма платежа
            "value": f"{amount:.2f}", # str(Decimal) - обязательная строка: "100.00"
            "currency": "RUB",
        },
        "confirmation": { # Как подтвердить платёж
            "type": "redirect", # Пользователь перенаправляется на форму Yookassa
            "return_url": YOOKASSA_RETURN_URL, # Куда вернуть пользователя после оплаты  
        },
        "capture": True, # Автоматическое списание денег после авторизации
        "description": description, # Видно пользователю в истории
        "metadata": { # Мои данные (сохраняются в платеже)
            "order_id": order_id, # Связь с заказом из БД
        },
        "receipt": { # ФИСКальный чек, т.е документ (обязателен по 54-ФЗ для РФ)
            "customer": { # Данные плательщика
                "email": user_email, # Чек придет на email
            },
            "items": [
                # Список товаров/услуг (здесь 1 item = весь наш заказ)
                # Но также можно передать и каждую позицию отдельно.
                {
                    "description": description[:128], # Максимальное кол-во символов - 128.
                    "quantity": "1.00", # Количество (строка)
                    "amount": { # Сумма item
                        "value": f"{amount:.2f}",
                        "currency": "RUB",
                        
                    },
                    "vat_code": 1, # НДС: 1=без НДС (0%), 2=0%, 3=10%, 4=20%, 5=расчетный, 6=спецрежим
                    "payment_mode": "full_prepayment", # Режим: полная предоплата
                    "payment_subject": "commodity", # Тип: "service"=услуга, "commodity"=товар или заказ 
                },
            ],
        },
    }
    
    # Вспомогательная синхронная функция для создания платежа
    def _request() -> Payment:
        # Payment.create(payload, idempotence_key) - POST-запрос к API Yookassa
        # uuid4(): - уникальный ключ, если повтор - вернет существующий платеж (идемпотентность)
        return Payment.create(payload, str(uuid4()))
    
    # Вызов в thread (библиотека YooKassa синхронная, а FastAPI - асинхронный)
    payment: Payment = await to_thread.run_sync(_request)
    
    # Извлечение URL для оплаты
    confirmation_url = getattr(payment.confirmation, "confirmation_url", None)
    
    # Возврат данных для фронта/БД
    return {
        # ID платежа, полученного от YooKassa
        "id": payment.id,
        # Статус платежа, пока он будет "pending"
        "status": payment.status,
        # Ссылка на оплату (сюда пользователя перенаправит для оплаты)
        "confirmation_url": confirmation_url,
    }
        
    
     

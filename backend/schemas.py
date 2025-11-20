from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Literal
from datetime import datetime

# Schemas define our collections implicitly:
# class name lowercased => collection name

class User(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    email: EmailStr
    password_hash: str
    full_name: Optional[str] = None
    kyc_status: Literal["pending", "approved", "rejected"] = "pending"
    kyc_submitted_at: Optional[datetime] = None
    is_admin: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class Wallet(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str
    asset: Literal["BTC", "ETH", "USDT"]
    address: str
    balance: float = 0.0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class Deposit(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str
    asset: Literal["BTC", "ETH", "USDT"]
    amount: float
    txid: Optional[str] = None
    status: Literal["pending", "completed", "failed"] = "pending"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class Withdrawal(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str
    asset: Literal["BTC", "ETH", "USDT"]
    amount: float
    to_address: str
    status: Literal["pending", "approved", "rejected", "sent"] = "pending"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class Order(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str
    side: Literal["buy", "sell"]
    pair: Literal["BTC-USDT", "ETH-USDT"]
    type: Literal["market"] = "market"
    amount: float  # base asset amount for market orders
    price_executed: Optional[float] = None
    status: Literal["filled", "rejected"] = "filled"
    created_at: Optional[datetime] = None

class Trade(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    buy_order_id: str
    sell_order_id: str
    pair: Literal["BTC-USDT", "ETH-USDT"]
    price: float
    amount: float
    created_at: Optional[datetime] = None

class KYCSubmission(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str
    document_type: str
    document_number: str
    status: Literal["pending", "approved", "rejected"] = "pending"
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None

class P2POffer(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str
    asset: Literal["BTC", "ETH", "USDT"]
    side: Literal["buy", "sell"]
    price: float
    min_amount: float
    max_amount: float
    payment_methods: List[str] = []
    status: Literal["active", "paused", "filled", "cancelled"] = "active"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class P2PTrade(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    offer_id: str
    buyer_id: str
    seller_id: str
    asset: Literal["BTC", "ETH", "USDT"]
    amount: float
    price: float
    status: Literal["escrow", "released", "cancelled"] = "escrow"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class EarnProduct(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    asset: Literal["BTC", "ETH", "USDT"]
    apy: float
    lock_days: int
    status: Literal["active", "inactive"] = "active"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class EarnSubscription(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str
    product_id: str
    amount: float
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Literal["accruing", "redeemed", "cancelled"] = "accruing"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

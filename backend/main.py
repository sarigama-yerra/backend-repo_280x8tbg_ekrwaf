from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext
import httpx
import os

from schemas import User, Wallet, Deposit, Withdrawal, Order, Trade, KYCSubmission, P2POffer, P2PTrade, EarnProduct, EarnSubscription
from database import create_document, get_documents, get_document, update_document

SECRET_KEY = os.getenv("SECRET_KEY", "secret")
ALGO = "HS256"
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="Lavo Exchange API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------- Auth Helpers ---------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class AuthUser(BaseModel):
    id: str
    email: EmailStr
    is_admin: bool = False

async def authenticate(token: str) -> AuthUser:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGO])
        return AuthUser(**payload)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# -------- Utility ---------
ASSETS = ["BTC", "ETH", "USDT"]
PAIRS = ["BTC-USDT", "ETH-USDT"]

async def ensure_wallets(user_id: str):
    for asset in ASSETS:
        existing = await get_document("wallet", {"user_id": user_id, "asset": asset})
        if not existing:
            await create_document("wallet", {
                "user_id": user_id,
                "asset": asset,
                "address": f"{asset}_ADDR_{user_id[-6:]}",
                "balance": 0.0
            })

async def get_price(pair: str) -> float:
    # Use Binance public price as simple feed
    symbol = pair.replace("-", "")
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
        return float(data["price"])

# -------- Auth Routes ---------
class RegisterBody(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

@app.post("/auth/register")
async def register(body: RegisterBody):
    existing = await get_document("user", {"email": body.email})
    if existing:
        raise HTTPException(400, "Email already registered")
    user_id = await create_document("user", {
        "email": body.email,
        "password_hash": pwd.hash(body.password),
        "full_name": body.full_name,
        "kyc_status": "pending",
        "kyc_submitted_at": None,
        "is_admin": False
    })
    await ensure_wallets(user_id)
    token = jwt.encode({"id": user_id, "email": body.email, "is_admin": False}, SECRET_KEY, algorithm=ALGO)
    return {"token": token}

class LoginBody(BaseModel):
    email: EmailStr
    password: str

@app.post("/auth/login")
async def login(body: LoginBody):
    user = await get_document("user", {"email": body.email})
    if not user or not pwd.verify(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    token = jwt.encode({"id": user["_id"], "email": user["email"], "is_admin": user.get("is_admin", False)}, SECRET_KEY, algorithm=ALGO)
    return {"token": token}

# -------- KYC ---------
class KYCBody(BaseModel):
    document_type: str
    document_number: str

async def auto_approve_kyc(user_id: str):
    await update_document("user", {"_id": user_id}, {"kyc_status": "approved"})
    await create_document("kycsubmission", {
        "user_id": user_id,
        "document_type": "auto",
        "document_number": "n/a",
        "status": "approved",
        "submitted_at": datetime.utcnow(),
        "reviewed_at": datetime.utcnow()
    })

@app.post("/kyc/submit")
async def kyc_submit(body: KYCBody, token: str):
    au = await authenticate(token)
    await update_document("user", {"_id": au.id}, {"kyc_status": "pending", "kyc_submitted_at": datetime.utcnow()})
    # simulate delayed approval via background task after 60s
    # In this environment, we'll set immediate approval if env FAST_KYC=1
    fast = os.getenv("FAST_KYC", "0") == "1"
    delay = 0 if fast else 60
    # We can't actually sleep in background; we'll just approve immediately for demo
    await auto_approve_kyc(au.id)
    return {"status": "submitted"}

@app.get("/me")
async def me(token: str):
    au = await authenticate(token)
    user = await get_document("user", {"_id": au.id})
    wallets = await get_documents("wallet", {"user_id": au.id}, limit=10)
    return {"user": user, "wallets": wallets}

# -------- Deposits ---------
class DepositBody(BaseModel):
    asset: str
    amount: float

@app.post("/deposit")
async def deposit(body: DepositBody, token: str):
    au = await authenticate(token)
    if body.asset not in ASSETS:
        raise HTTPException(400, "Unsupported asset")
    dep_id = await create_document("deposit", {
        "user_id": au.id,
        "asset": body.asset,
        "amount": body.amount,
        "status": "completed"
    })
    # credit wallet
    w = await get_document("wallet", {"user_id": au.id, "asset": body.asset})
    new_bal = float(w.get("balance", 0)) + body.amount
    await update_document("wallet", {"_id": w["_id"]}, {"balance": new_bal})
    return {"deposit_id": dep_id}

# -------- Withdrawals ---------
class WithdrawalBody(BaseModel):
    asset: str
    amount: float
    to_address: str

@app.post("/withdraw")
async def withdraw(body: WithdrawalBody, token: str):
    au = await authenticate(token)
    if body.asset not in ASSETS:
        raise HTTPException(400, "Unsupported asset")
    w = await get_document("wallet", {"user_id": au.id, "asset": body.asset})
    if not w or float(w.get("balance", 0)) < body.amount:
        raise HTTPException(400, "Insufficient balance")
    # create withdrawal pending admin approval
    wd_id = await create_document("withdrawal", {
        "user_id": au.id,
        "asset": body.asset,
        "amount": body.amount,
        "to_address": body.to_address,
        "status": "pending"
    })
    return {"withdrawal_id": wd_id, "status": "pending"}

class ApproveBody(BaseModel):
    withdrawal_id: str
    approve: bool = True

@app.post("/admin/withdrawals/approve")
async def approve_withdrawal(body: ApproveBody, token: str):
    au = await authenticate(token)
    if not au.is_admin:
        raise HTTPException(403, "Admin only")
    wd = await get_document("withdrawal", {"_id": body.withdrawal_id})
    if not wd:
        raise HTTPException(404, "Not found")
    if body.approve:
        # debit user balance and mark sent
        w = await get_document("wallet", {"user_id": wd["user_id"], "asset": wd["asset"]})
        if float(w.get("balance", 0)) < float(wd["amount"]):
            raise HTTPException(400, "Insufficient funds at approval")
        await update_document("wallet", {"_id": w["_id"]}, {"balance": float(w.get("balance", 0)) - float(wd["amount"])})
        await update_document("withdrawal", {"_id": wd["_id"]}, {"status": "sent"})
    else:
        await update_document("withdrawal", {"_id": wd["_id"]}, {"status": "rejected"})
    return {"status": "ok"}

@app.get("/withdrawals")
async def list_withdrawals(token: str):
    au = await authenticate(token)
    flt = {} if au.is_admin else {"user_id": au.id}
    wds = await get_documents("withdrawal", flt, limit=100, sort=[["created_at", -1]])
    return wds

# -------- Market Trading ---------
class OrderBody(BaseModel):
    side: str  # buy/sell
    pair: str  # BTC-USDT
    amount: float

@app.post("/trade/order")
async def market_order(body: OrderBody, token: str):
    au = await authenticate(token)
    if body.pair not in PAIRS:
        raise HTTPException(400, "Unsupported pair")
    price = await get_price(body.pair)
    base, quote = body.pair.split("-")
    if body.side == "buy":
        # need quote balance
        q_wallet = await get_document("wallet", {"user_id": au.id, "asset": quote})
        cost = body.amount * price
        if float(q_wallet.get("balance", 0)) < cost:
            raise HTTPException(400, "Insufficient quote balance")
        await update_document("wallet", {"_id": q_wallet["_id"]}, {"balance": float(q_wallet["balance"]) - cost})
        b_wallet = await get_document("wallet", {"user_id": au.id, "asset": base})
        await update_document("wallet", {"_id": b_wallet["_id"]}, {"balance": float(b_wallet.get("balance", 0)) + body.amount})
    elif body.side == "sell":
        b_wallet = await get_document("wallet", {"user_id": au.id, "asset": base})
        if float(b_wallet.get("balance", 0)) < body.amount:
            raise HTTPException(400, "Insufficient base balance")
        await update_document("wallet", {"_id": b_wallet["_id"]}, {"balance": float(b_wallet.get("balance", 0)) - body.amount})
        q_wallet = await get_document("wallet", {"user_id": au.id, "asset": quote})
        proceeds = body.amount * price
        await update_document("wallet", {"_id": q_wallet["_id"]}, {"balance": float(q_wallet.get("balance", 0)) + proceeds})
    else:
        raise HTTPException(400, "Invalid side")
    order_id = await create_document("order", {
        "user_id": au.id,
        "side": body.side,
        "pair": body.pair,
        "amount": body.amount,
        "price_executed": price,
        "status": "filled",
        "created_at": datetime.utcnow(),
    })
    return {"order_id": order_id, "price": price}

@app.get("/prices")
async def prices():
    out = {}
    for p in PAIRS:
        try:
            out[p] = await get_price(p)
        except Exception:
            out[p] = None
    return out

# -------- P2P ---------
class OfferBody(BaseModel):
    asset: str
    side: str
    price: float
    min_amount: float
    max_amount: float
    payment_methods: List[str] = []

@app.post("/p2p/offer")
async def create_offer(body: OfferBody, token: str):
    au = await authenticate(token)
    if body.asset not in ASSETS or body.side not in ["buy", "sell"]:
        raise HTTPException(400, "Invalid offer")
    offer_id = await create_document("p2poffer", {
        "user_id": au.id,
        "asset": body.asset,
        "side": body.side,
        "price": body.price,
        "min_amount": body.min_amount,
        "max_amount": body.max_amount,
        "payment_methods": body.payment_methods,
        "status": "active"
    })
    return {"offer_id": offer_id}

@app.get("/p2p/offers")
async def list_offers(asset: Optional[str] = None, side: Optional[str] = None):
    flt = {}
    if asset:
        flt["asset"] = asset
    if side:
        flt["side"] = side
    offers = await get_documents("p2poffer", flt, limit=200, sort=[["created_at", -1]])
    return offers

class P2PDealBody(BaseModel):
    offer_id: str
    amount: float

@app.post("/p2p/deal")
async def p2p_deal(body: P2PDealBody, token: str):
    au = await authenticate(token)
    offer = await get_document("p2poffer", {"_id": body.offer_id})
    if not offer or offer["status"] != "active":
        raise HTTPException(400, "Offer not available")
    if body.amount < float(offer["min_amount"]) or body.amount > float(offer["max_amount"]):
        raise HTTPException(400, "Amount out of bounds")
    # reserve escrow from seller when sell offer; from buyer when buy offer
    if offer["side"] == "sell":
        seller_id = offer["user_id"]
        buyer_id = au.id
    else:
        seller_id = au.id
        buyer_id = offer["user_id"]
    w = await get_document("wallet", {"user_id": seller_id, "asset": offer["asset"]})
    if float(w.get("balance", 0)) < body.amount:
        raise HTTPException(400, "Insufficient escrow funds")
    await update_document("wallet", {"_id": w["_id"]}, {"balance": float(w.get("balance", 0)) - body.amount})
    trade_id = await create_document("p2ptrade", {
        "offer_id": offer["_id"],
        "buyer_id": buyer_id,
        "seller_id": seller_id,
        "asset": offer["asset"],
        "amount": body.amount,
        "price": offer["price"],
        "status": "escrow"
    })
    return {"trade_id": trade_id}

class P2PReleaseBody(BaseModel):
    trade_id: str

@app.post("/p2p/release")
async def p2p_release(body: P2PReleaseBody, token: str):
    au = await authenticate(token)
    trade = await get_document("p2ptrade", {"_id": body.trade_id})
    if not trade or trade["status"] != "escrow":
        raise HTTPException(400, "Invalid trade")
    # only seller can release
    if trade["seller_id"] != au.id:
        raise HTTPException(403, "Only seller can release")
    # credit buyer wallet
    w = await get_document("wallet", {"user_id": trade["buyer_id"], "asset": trade["asset"]})
    await update_document("wallet", {"_id": w["_id"]}, {"balance": float(w.get("balance", 0)) + float(trade["amount"])})
    await update_document("p2ptrade", {"_id": trade["_id"]}, {"status": "released"})
    return {"status": "released"}

# -------- Earn ---------
class CreateProductBody(BaseModel):
    asset: str
    apy: float
    lock_days: int

@app.post("/earn/product")
async def create_product(body: CreateProductBody, token: str):
    au = await authenticate(token)
    if not au.is_admin:
        raise HTTPException(403, "Admin only")
    if body.asset not in ASSETS:
        raise HTTPException(400, "Invalid asset")
    pid = await create_document("earnproduct", {
        "asset": body.asset,
        "apy": body.apy,
        "lock_days": body.lock_days,
        "status": "active"
    })
    return {"product_id": pid}

@app.get("/earn/products")
async def list_products():
    return await get_documents("earnproduct", {"status": "active"}, limit=100)

class SubscribeBody(BaseModel):
    product_id: str
    amount: float

@app.post("/earn/subscribe")
async def subscribe(body: SubscribeBody, token: str):
    au = await authenticate(token)
    prod = await get_document("earnproduct", {"_id": body.product_id, "status": "active"})
    if not prod:
        raise HTTPException(404, "Product not found")
    w = await get_document("wallet", {"user_id": au.id, "asset": prod["asset"]})
    if float(w.get("balance", 0)) < body.amount:
        raise HTTPException(400, "Insufficient balance")
    await update_document("wallet", {"_id": w["_id"]}, {"balance": float(w.get("balance", 0)) - body.amount})
    sid = await create_document("earnsubscription", {
        "user_id": au.id,
        "product_id": body.product_id,
        "amount": body.amount,
        "start_date": datetime.utcnow(),
        "status": "accruing"
    })
    return {"subscription_id": sid}

@app.post("/earn/redeem")
async def redeem(subscription_id: str, token: str):
    au = await authenticate(token)
    sub = await get_document("earnsubscription", {"_id": subscription_id, "user_id": au.id})
    if not sub or sub["status"] != "accruing":
        raise HTTPException(400, "Invalid subscription")
    prod = await get_document("earnproduct", {"_id": sub["product_id"]})
    days = (datetime.utcnow() - sub.get("start_date", datetime.utcnow())).days
    apy = float(prod["apy"]) / 100.0
    reward = float(sub["amount"]) * apy * (days / 365)
    # credit back principal + reward
    w = await get_document("wallet", {"user_id": au.id, "asset": prod["asset"]})
    await update_document("wallet", {"_id": w["_id"]}, {"balance": float(w.get("balance", 0)) + float(sub["amount"]) + reward})
    await update_document("earnsubscription", {"_id": sub["_id"]}, {"status": "redeemed", "end_date": datetime.utcnow()})
    return {"redeemed": True, "reward": reward}

@app.get("/test")
async def test():
    # quick DB health check
    users = await get_documents("user", {}, limit=1)
    return {"ok": True, "users_count_preview": len(users)}

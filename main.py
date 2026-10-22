from fastapi import FastAPI

from routers.auth import router as auth_router
from routers.audit_logs import router as audit_logs_router
from routers.categories import router as categories_router
from routers.inventory import router as inventory_router
from routers.products import router as products_router
from routers.product_returns import router as product_returns_router
from routers.reports import router as reports_router
from routers.purchase_orders import router as purchase_orders_router
from routers.sales_orders import router as sales_orders_router
from routers.stock_transfers import router as stock_transfers_router
from routers.suppliers import router as suppliers_router
from routers.users import router as users_router
from routers.warehouses import router as warehouses_router

app = FastAPI(
    title="Branch Retail, Inventory & Procurement Management System",
    description="Backend APIs for retail operations, inventory, procurement, and sales.",
    version="1.0.0",
)

app.include_router(auth_router)
app.include_router(audit_logs_router)
app.include_router(users_router)
app.include_router(categories_router)
app.include_router(products_router)
app.include_router(product_returns_router)
app.include_router(reports_router)
app.include_router(suppliers_router)
app.include_router(warehouses_router)
app.include_router(inventory_router)
app.include_router(purchase_orders_router)
app.include_router(sales_orders_router)
app.include_router(stock_transfers_router)


@app.get("/", tags=["Health"])
def health_check():
    return {"message": "Branch Retail Management API is running"}

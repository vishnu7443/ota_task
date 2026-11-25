from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SalesmanProfile(Base):
    __tablename__ = "salesman_profiles"
    __table_args__ = ({"schema": "sales"},)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    employee_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    territory: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint("customer_type IN ('RETAILER', 'DISTRIBUTOR')", name="customer_type_enum"),
        CheckConstraint(
            "gstin IS NULL OR gstin ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$'",
            name="gstin_format",
        ),
        CheckConstraint("primary_state_code ~ '^[0-9]{2}$'", name="state_code_format"),
        CheckConstraint(
            "gstin IS NULL OR SUBSTRING(gstin FROM 1 FOR 2) = primary_state_code",
            name="gstin_matches_state",
        ),
        CheckConstraint("credit_days >= 0", name="credit_days_non_negative"),
        Index("idx_customers_salesman_active", "assigned_salesman_id", "is_active"),
        {"schema": "sales"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    customer_type: Mapped[str] = mapped_column(String(20), nullable=False)
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    primary_state_name: Mapped[str] = mapped_column(String(80), nullable=False)
    primary_state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    assigned_salesman_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    credit_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    addresses: Mapped[list["CustomerAddress"]] = relationship(back_populates="customer")


class CustomerAddress(Base):
    __tablename__ = "customer_addresses"
    __table_args__ = (
        CheckConstraint("address_type IN ('BILLING', 'SHIPPING')", name="address_type_enum"),
        CheckConstraint("state_code ~ '^[0-9]{2}$'", name="addr_state_code_format"),
        CheckConstraint("pincode ~ '^[0-9]{6}$'", name="addr_pincode_format"),
        Index(
            "uq_cust_addr_default",
            "customer_id",
            "address_type",
            unique=True,
            postgresql_where=text("is_default IS TRUE"),
        ),
        {"schema": "sales"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.customers.id", ondelete="RESTRICT"), nullable=False
    )
    address_type: Mapped[str] = mapped_column(String(16), nullable=False)
    line1: Mapped[str] = mapped_column(String(200), nullable=False)
    line2: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str] = mapped_column(String(80), nullable=False)
    state_name: Mapped[str] = mapped_column(String(80), nullable=False)
    state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    pincode: Mapped[str] = mapped_column(String(6), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    customer: Mapped[Customer] = relationship(back_populates="addresses")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("hsn_code ~ '^[0-9]{4,8}$'", name="hsn_format"),
        CheckConstraint(
            "gst_rate_bps >= 0 AND gst_rate_bps <= 2800 AND gst_rate_bps % 2 = 0",
            name="gst_rate_valid",
        ),
        {"schema": "sales"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    hsn_code: Mapped[str] = mapped_column(String(12), nullable=False)
    gst_rate_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    pack_sizes: Mapped[list["PackSize"]] = relationship(back_populates="product")


class PackSize(Base):
    __tablename__ = "pack_sizes"
    __table_args__ = (
        CheckConstraint("pack_weight_g > 0", name="pack_weight_positive"),
        CheckConstraint("packets_per_carton > 0", name="carton_ratio_positive"),
        CheckConstraint("base_selling_price_paisa >= 0", name="base_price_non_negative"),
        UniqueConstraint("product_id", "pack_weight_g", name="uq_pack_sizes_product_weight"),
        {"schema": "sales"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.products.id", ondelete="RESTRICT"), nullable=False
    )
    sku_code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(140), nullable=False)
    pack_weight_g: Mapped[int] = mapped_column(Integer, nullable=False)
    packets_per_carton: Mapped[int] = mapped_column(Integer, nullable=False)
    base_selling_price_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    product: Mapped[Product] = relationship(back_populates="pack_sizes")


class PriceList(Base):
    __tablename__ = "price_lists"
    __table_args__ = (
        CheckConstraint(
            "NOT (is_default AND customer_id IS NOT NULL)", name="default_not_customer_specific"
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from", name="valid_date_window"
        ),
        Index(
            "uq_pricelist_single_default",
            "is_default",
            unique=True,
            postgresql_where=text("is_default IS TRUE AND is_active IS TRUE"),
        ),
        {"schema": "sales"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    customer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sales.customers.id", ondelete="RESTRICT"), nullable=True
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    items: Mapped[list["PriceListItem"]] = relationship(back_populates="price_list")


class PriceListItem(Base):
    __tablename__ = "price_list_items"
    __table_args__ = (
        CheckConstraint("unit_price_paisa >= 0", name="unit_price_non_negative"),
        CheckConstraint("min_qty >= 1", name="min_qty_positive"),
        UniqueConstraint("price_list_id", "pack_size_id", "min_qty", name="uq_pli_list_sku_qty"),
        {"schema": "sales"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    price_list_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.price_lists.id", ondelete="RESTRICT"), nullable=False
    )
    pack_size_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.pack_sizes.id", ondelete="RESTRICT"), nullable=False
    )
    unit_price_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    min_qty: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    price_list: Mapped[PriceList] = relationship(back_populates="items")

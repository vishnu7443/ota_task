from pydantic import BaseModel


class CustomerAddressResponse(BaseModel):
    id: int
    address_type: str
    line1: str
    line2: str | None = None
    city: str
    state_name: str
    state_code: str
    pincode: str


class CustomerSummary(BaseModel):
    id: int
    code: str
    name: str
    customer_type: str
    gstin: str | None = None
    primary_state_name: str
    primary_state_code: str
    phone: str | None = None
    assigned_salesman_id: int | None = None
    default_shipping_address: CustomerAddressResponse | None = None


class ProductPackResponse(BaseModel):
    pack_size_id: int
    product_id: int
    product_code: str
    sku_code: str
    product_name: str
    display_name: str
    category: str
    hsn_code: str
    gst_rate_bps: int
    pack_weight_g: int
    packets_per_carton: int
    selling_price_paisa: int
    available_stock_pkts: int
    on_hand_stock_pkts: int


class SalesmanOption(BaseModel):
    user_id: int
    full_name: str
    employee_code: str
    territory: str | None = None


class CustomerCreateRequest(BaseModel):
    code: str
    name: str
    customer_type: str  # RETAILER | DISTRIBUTOR
    gstin: str | None = None
    primary_state_name: str
    primary_state_code: str
    phone: str | None = None
    assigned_salesman_id: int | None = None
    credit_days: int = 30
    address_line1: str
    city: str
    pincode: str


class PackSizePriceUpdateRequest(BaseModel):
    unit_price_paisa: int
    reason: str

"""
POS Cashier - Streamlit Order Automation
=========================================
Full-featured UI to create orders via the POS API.
Fetches real categories & dishes, supports all order types,
and can recreate previous orders.

Run: streamlit run pos_app.py
"""

import streamlit as st
import requests
import json
import time
from datetime import datetime

# ─── Page Config ───
st.set_page_config(
    page_title="POS Order Automation",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── Custom CSS ───
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/icon?family=Material+Icons');
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
    .material-icons {
        font-family: 'Material Icons' !important;
        font-style: normal;
        font-weight: normal;
        font-size: 20px;
        line-height: 1;
        display: inline-block;
        text-rendering: optimizeLegibility;
        -webkit-font-smoothing: antialiased;
    }
    .stApp { background-color: #f5f6fa; }
    .main-header {
        background: linear-gradient(90deg, #e94560, #c23152);
        padding: 20px 30px; border-radius: 12px; margin-bottom: 20px;
        color: white; text-align: center;
    }
    .main-header h1 { margin: 0; font-size: 28px; }
    .main-header p { margin: 4px 0 0; opacity: 0.85; font-size: 14px; }
    .order-card {
        background: #ffffff; border: 1px solid #dde1ea; border-radius: 12px;
        padding: 20px; margin-bottom: 16px;
    }
    .result-success { background: #edfbf3; border: 1px solid #34c770; border-radius: 10px; padding: 14px; margin: 8px 0; }
    .result-fail { background: #fff0f2; border: 1px solid #e94560; border-radius: 10px; padding: 14px; margin: 8px 0; }
    .stat-card {
        background: #ffffff; border: 1px solid #dde1ea; border-radius: 10px;
        padding: 16px; text-align: center;
    }
    .stSelectbox label, .stNumberInput label, .stTextInput label, .stTextArea label {
        color: #444 !important;
    }
    div[data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid #dde1ea; }
</style>
""", unsafe_allow_html=True)


# ─── IP Whitelist ───
def check_ip():
    try:
        headers = st.context.headers
        client_ip = (
            headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or headers.get("X-Real-Ip", "").strip()
            or "unknown"
        )
        allowed = st.secrets.get("allowed_ips", ["*"])
        if "*" in allowed:
            return  # allow everyone
        if client_ip not in allowed:
            st.error(f"⛔ Access Denied — IP `{client_ip}` is not authorized.")
            st.info("Contact the system administrator to add your IP.")
            st.stop()
    except Exception:
        pass

check_ip()


# ─── Session State Init ───
def init_state():
    defaults = {
        "token": "",
        "base_url": "http://192.168.11.101:8000",
        "branch_id": 3,
        "machine_id": "3",
        "categories": [],
        "dishes": {},  # {category_id: [dishes]}
        "tables": [],  # available tables
        "areas": [],   # delivery areas
        "orders_history": [],  # completed orders
        "connected": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()


# ─── API Functions ───
def api_headers():
    return {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {st.session_state.token}",
        "lang": "ar",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) cashier/0.0.0 Chrome/140.0.7339.249 Electron/38.7.2 Safari/537.36",
        "ngrok-skip-browser-warning": "true",
    }


def fetch_categories():
    """Fetch menu categories from API."""
    try:
        url = f"{st.session_state.base_url}/api/menu-categories-lite?branchId={st.session_state.branch_id}"
        r = requests.get(url, headers=api_headers(), timeout=15)
        data = r.json()
        
        cats = []
        # Unwrap response
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    cats.append(item)
        elif isinstance(data, dict):
            for v in data.values():
                if isinstance(v, dict):
                    cats.append(v)
                elif isinstance(v, list):
                    for sub in v:
                        if isinstance(sub, dict):
                            cats.append(sub)
        return cats
    except Exception as e:
        st.error(f"Failed to fetch categories: {e}")
        return []


def extract_dishes(data):
    """Safely extract a flat list of dish dicts from the API response.
    
    API format: data.data.dishes[] where each entry is:
    { "dish": {...}, "sizes": [...], "addon_categories": [...] }
    
    We merge dish + sizes + addon_categories into a single dict.
    """
    dishes = []
    
    # Unwrap response envelope
    if isinstance(data, dict):
        if "data" in data:
            data = data["data"]
    
    # data is now the category object with a "dishes" key
    raw_dishes = []
    if isinstance(data, dict) and "dishes" in data:
        raw_dishes = data["dishes"]
    elif isinstance(data, list):
        raw_dishes = data
    
    for item in raw_dishes:
        if not isinstance(item, dict):
            continue
        
        # The dish info is inside a "dish" key
        if "dish" in item and isinstance(item["dish"], dict):
            dish = dict(item["dish"])
            # Merge sizes and addon_categories from the wrapper
            dish["sizes"] = item.get("sizes", [])
            dish["addon_categories"] = item.get("addon_categories", [])
            dishes.append(dish)
        elif "id" in item or "dish_id" in item:
            # Already a flat dish dict
            dishes.append(item)
    
    return dishes


def fetch_dishes(category_id):
    """Fetch dishes for a specific category."""
    try:
        url = f"{st.session_state.base_url}/api/menu-dishes-lite?categoryId={category_id}&branchId={st.session_state.branch_id}"
        r = requests.get(url, headers=api_headers(), timeout=15)
        data = r.json()
        return extract_dishes(data)
    except Exception as e:
        st.error(f"Failed to fetch dishes: {e}")
        return []


def fetch_all_dishes():
    """Fetch all dishes from all categories."""
    try:
        url = f"{st.session_state.base_url}/api/menu-dishes?branchId={st.session_state.branch_id}"
        r = requests.get(url, headers=api_headers(), timeout=30)
        data = r.json()
        return extract_dishes(data)
    except Exception as e:
        return []


def fetch_tables():
    """Fetch tables from API."""
    try:
        url = f"{st.session_state.base_url}/api/tables/index"
        r = requests.get(url, headers=api_headers(), timeout=15)
        data = r.json()

        # Unwrap response
        if isinstance(data, dict) and "data" in data:
            data = data["data"]

        tables = []
        raw_list = data if isinstance(data, list) else []

        # If data is a dict with nested lists, try to find tables
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list):
                    raw_list = v
                    break

        for t in raw_list:
            if not isinstance(t, dict):
                continue
            # Table might be nested inside a "table" key
            tbl = t.get("table", t) if isinstance(t.get("table"), dict) else t
            tid = tbl.get("id") or tbl.get("table_id")
            tname = tbl.get("name") or tbl.get("table_name") or tbl.get("number") or f"Table {tid}"
            tstatus = tbl.get("status") or t.get("status") or "unknown"
            tzone = tbl.get("zone") or tbl.get("area") or tbl.get("section") or ""

            # API returns available_status as boolean (true = available, status int 1 = active)
            raw_avail = tbl.get("available_status")
            if raw_avail is None:
                raw_avail = t.get("available_status")
            if raw_avail is not None:
                is_available = bool(raw_avail)
            else:
                # Fallback: integer status 1 means available
                is_available = (tstatus == 1 or str(tstatus).lower() in ("available", "متاحة", "free", ""))

            if tid is not None:
                tables.append({
                    "id": tid,
                    "name": tname,
                    "status": tstatus,
                    "zone": tzone,
                    "is_available": is_available,
                })
        return tables
    except Exception as e:
        return []


def fetch_areas():
    """Fetch delivery areas from API."""
    try:
        url = f"{st.session_state.base_url}/api/areas/{st.session_state.branch_id}"
        r = requests.get(url, headers=api_headers(), timeout=15)
        data = r.json()
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        raw = data if isinstance(data, list) else (data.get("data", []) if isinstance(data, dict) else [])
        areas = []
        for a in raw:
            if isinstance(a, dict):
                aid = a.get("id")
                aname = a.get("name") or a.get("name_ar") or f"Area {aid}"
                if aid:
                    areas.append({"id": aid, "name": aname})
        # Fallback to getAllAreas if branch areas empty
        if not areas:
            url2 = f"{st.session_state.base_url}/api/getAllAreas"
            r2 = requests.get(url2, headers=api_headers(), timeout=15)
            data2 = r2.json()
            if isinstance(data2, dict) and "data" in data2:
                data2 = data2["data"]
            raw2 = data2 if isinstance(data2, list) else (data2.get("data", []) if isinstance(data2, dict) else [])
            for a in raw2:
                if isinstance(a, dict):
                    aid = a.get("id")
                    aname = a.get("name") or a.get("name_ar") or f"Area {aid}"
                    if aid:
                        areas.append({"id": aid, "name": aname})
        return areas
    except Exception as e:
        return []


def create_delivery_address(delivery_info):
    """Create a client address via API and return (address_id, error)."""
    try:
        addr_type_map = {"شقة": "apartment", "فيلا": "villa", "مكتب": "office", "فندق": "hotel"}
        addr_type = addr_type_map.get(delivery_info.get("addr_type", "شقة"), "apartment")
        payload = {
            "address": delivery_info.get("address", ""),
            "address_type": addr_type,
            "address_phone": delivery_info.get("phone", ""),
            "country_code": delivery_info.get("country_code", "20"),
            "client_name": delivery_info.get("client_name", "عميل"),
            "area_id": delivery_info.get("area_id"),
            "building": delivery_info.get("building", ""),
            "floor_number": delivery_info.get("floor", ""),
            "apartment_number": delivery_info.get("apartment", ""),
            "notes": delivery_info.get("notes", ""),
        }
        r = requests.post(
            f"{st.session_state.base_url}/api/cashier/add/address",
            json=payload, headers=api_headers(), timeout=30
        )
        try:
            data = r.json()
        except Exception:
            return None, f"HTTP {r.status_code}: non-JSON response: {r.text[:300]}"
        if data.get("status") == True:
            return data["data"]["address_id"], None
        msg = data.get("message") or ""
        errs = data.get("errorData") or data.get("errors") or {}
        detail = f"HTTP {r.status_code}: {msg}"
        if errs:
            detail += f" | {json.dumps(errs, ensure_ascii=False)}"
        return None, detail
    except Exception as e:
        return None, str(e)


def build_item(dish, quantity, note="", selected_addons=None, size_id=None, size_name=""):
    """Build an item payload from a dish object."""
    addons_list = selected_addons or []
    addon_total = sum(a.get("price", 0) for a in addons_list)

    item = {
        "dish_id": dish.get("id") or dish.get("dish_id"),
        "dish_name": dish.get("name") or dish.get("dish_name", ""),
        "dish_description": dish.get("description") or dish.get("dish_description", ""),
        "dish_price": float(dish.get("price") or dish.get("dish_price", 0)),
        "currency_symbol": "ج.م",
        "dish_image": dish.get("image") or dish.get("dish_image"),
        "category": dish.get("category_id") or dish.get("category", 1),
        "quantity": quantity,
        "sizeId": size_id,
        "size": "",
        "sizeName": size_name,
        "sizeDescription": "",
        "note": note,
        "finalPrice": (float(dish.get("price") or dish.get("dish_price", 0)) + addon_total) * quantity,
        "selectedAddons": [{"id": a["id"], "name": a["name"], "price": a["price"], "currency_symbol": "ج.م"} for a in addons_list],
        "addon_categories": (lambda groups: [{"id": cid, "addon": aids} for cid, aids in groups.items()])(
            {a.get("category_id", 1): [x["id"] for x in addons_list if x.get("category_id", 1) == a.get("category_id", 1)] for a in addons_list}
        ) if addons_list else [],
    }
    return item


def build_payload(order_config):
    """Build the complete API payload."""
    items = order_config["items"]
    subtotal = sum(item["finalPrice"] for item in items)
    tax = round(subtotal * 0.14, 2)
    bill = round(subtotal + tax, 2)
    is_paid = order_config["payment"] != "unpaid"

    # Get tip settings
    tip_opt = order_config.get("tip_option", "no_tip")
    tip_amt = float(order_config.get("tip_amount", 0))
    paid_amount = float(order_config.get("paid_amount", 0))

    cash, credit, pay_amt, total = None, None, 0, 0
    change = 0
    returned = 0

    type_map = {"dine-in": "dine-in", "takeaway": "Takeaway", "delivery": "Delivery", "talabat": "talabat"}

    # dine-in has backend service fees; delivery has backend delivery fees.
    # The POS can't know these amounts, so skip cash/credit for those types
    # and let the backend handle totals via payment_status only.
    order_type_mapped = type_map.get(order_config["type"], order_config["type"])
    has_backend_fees = order_type_mapped in ("dine-in", "Delivery")

    if is_paid and not has_backend_fees:
        if order_config["payment"] == "cash_visa":
            cash = float(order_config.get("cash_amount", 0))
            credit = round(bill - cash, 2)
            pay_amt = bill
        elif order_config["payment"] == "visa":
            cash = 0
            credit = paid_amount if paid_amount > 0 else bill
            pay_amt = credit
        else:
            # Cash only — use the selected paid amount
            cash = paid_amount if paid_amount > 0 else bill
            credit = 0
            pay_amt = cash

        change = round(pay_amt - bill, 2) if pay_amt > bill else 0
        returned = round(change - tip_amt, 2) if change > tip_amt else 0
        total = pay_amt  # total_with_tip includes the overpayment

    # Map tip option to API field
    tips_aption = "no_tip"
    tip_specific = 0
    if is_paid:
        if tip_opt == "tip_the_change":
            tips_aption = "tip_the_change"
        elif tip_opt == "tip_specific_amount":
            tips_aption = "tip_specific_amount"
            tip_specific = tip_amt
        else:
            tips_aption = "no_tip"
    else:
        tips_aption = "tip_the_change"

    payload = {
        "isOnline": True,
        "orderId": int(time.time() * 1000),
        "order_id": None,
        "table_number": order_config.get("table_name"),
        "table_id": order_config.get("table_id"),
        "type": type_map.get(order_config["type"], order_config["type"]),
        "delivery_id": order_config.get("delivery_id"),
        "delivery_phone": order_config.get("delivery", {}).get("phone"),
        "delivery_area": order_config.get("delivery", {}).get("area"),
        "delivery_address": order_config.get("delivery", {}).get("address"),
        "delivery_address_type": order_config.get("delivery", {}).get("addr_type"),
        "address_id": order_config.get("address_id"),
        "branch_id": st.session_state.branch_id,
        "payment_method": "credit" if order_config["payment"] == "visa" else "cash",
        "payment_status": "paid" if is_paid else "unpaid",
        "cash_amount": cash,
        "credit_amount": credit,
        "cashier_machine_id": st.session_state.machine_id,
        "note": order_config.get("note", ""),
        "items": items,
        "change_amount": change,
        "tips_aption": tips_aption,
        "tip_amount": tip_amt,
        "tip_specific_amount": tip_specific,
        "payment_amount": pay_amt,
        "bill_amount": bill,
        "total_with_tip": total,
        "returned_amount": returned,
        "menu_integration": False,
        "payment_status_menu_integration": "paid" if is_paid else "unpaid",
        "coupon_code": " ",
    }

    if is_paid:
        pmi_map = {"cash": "cash", "visa": "credit", "cash_visa": "cash + credit"}
        payload["payment_method_menu_integration"] = pmi_map.get(order_config["payment"], "cash")

    if order_config.get("reference"):
        payload["reference_number"] = order_config["reference"]

    return payload, bill


def send_order(order_config):
    """Send order to API."""
    payload, bill = build_payload(order_config)
    try:
        r = requests.post(
            f"{st.session_state.base_url}/api/orders/cashier/store/api",
            json=payload, headers=api_headers(), timeout=60
        )
        try:
            data = r.json()
        except Exception:
            return {"success": False, "error": f"HTTP {r.status_code} — non-JSON response: {r.text[:400]}", "bill": bill}

        if data.get("status") == True:
            return {
                "success": True,
                "order_id": data["data"]["order_id"],
                "invoice_id": data["data"]["invoice_id"],
                "bill": bill,
            }
        # Collect all error detail the API returns
        msg = data.get("message") or data.get("error") or ""
        validation = data.get("errorData") or data.get("errors") or {}
        detail = f"HTTP {r.status_code}: {msg}"
        if validation:
            detail += f" | {json.dumps(validation, ensure_ascii=False)}"
        return {"success": False, "error": detail or "Unknown error", "bill": bill, "raw": data}
    except Exception as e:
        return {"success": False, "error": str(e), "bill": bill}


# ─── Sidebar ───
with st.sidebar:
    st.markdown("### ⚙️ Configuration")

    st.session_state.token = st.text_input(
        "🔑 Bearer Token",
        value=st.session_state.token,
        type="password",
        help="DevTools → Network → any request → Headers → Authorization"
    )

    st.session_state.base_url = st.text_input("🌐 Server URL", value=st.session_state.base_url)

    col1, col2 = st.columns(2)
    with col1:
        st.session_state.branch_id = st.number_input("Branch ID", value=st.session_state.branch_id, min_value=1)
    with col2:
        st.session_state.machine_id = st.text_input("Machine ID", value=st.session_state.machine_id)

    st.divider()

    # Connect button
    if st.button("🔌 Connect & Load Menu", use_container_width=True, type="primary"):
        if not st.session_state.token or len(st.session_state.token) < 50:
            st.error("Paste your Bearer token first!")
        else:
            with st.spinner("Loading menu data..."):
                cats = fetch_categories()
                if cats:
                    st.session_state.categories = cats
                    st.session_state.connected = True

                    # Fetch dishes for each category
                    dishes = {}
                    for cat in cats:
                        cat_id = cat.get("id")
                        if cat_id:
                            cat_dishes = fetch_dishes(cat_id)
                            if cat_dishes:
                                dishes[cat_id] = cat_dishes
                    st.session_state.dishes = dishes
                    st.success(f"✅ Loaded {len(cats)} categories, {sum(len(v) for v in dishes.values())} dishes")

                    # Fetch tables
                    tables = fetch_tables()
                    st.session_state.tables = tables
                    if tables:
                        st.success(f"✅ Loaded {len(tables)} tables")

                    # Fetch delivery areas
                    areas = fetch_areas()
                    st.session_state.areas = areas
                    if areas:
                        st.success(f"✅ Loaded {len(areas)} delivery areas")
                else:
                    st.error("Failed to load menu. Check token & server URL.")

    if st.session_state.connected:
        tbl_count = len(st.session_state.tables)
        st.success(f"✅ Connected • {len(st.session_state.categories)} categories • {tbl_count} tables")

    st.divider()
    st.markdown("### 📊 Stats")
    total_orders = len(st.session_state.orders_history)
    success_orders = sum(1 for o in st.session_state.orders_history if o.get("result", {}).get("success"))
    st.metric("Total Orders", total_orders)
    st.metric("Successful", success_orders)

    # Debug section
    with st.expander("🔧 Debug / Raw API Data"):
        if st.button("🔍 Show Raw Categories"):
            try:
                url = f"{st.session_state.base_url}/api/menu-categories-lite?branchId={st.session_state.branch_id}"
                r = requests.get(url, headers=api_headers(), timeout=15)
                st.json(r.json())
            except Exception as e:
                st.error(str(e))

        debug_cat_id = st.number_input("Category ID to debug", value=1, min_value=1)
        if st.button("🔍 Show Raw Dishes"):
            try:
                url = f"{st.session_state.base_url}/api/menu-dishes-lite?categoryId={debug_cat_id}&branchId={st.session_state.branch_id}"
                r = requests.get(url, headers=api_headers(), timeout=15)
                st.json(r.json())
            except Exception as e:
                st.error(str(e))

        if st.button("🔍 Show Raw Tables"):
            try:
                url = f"{st.session_state.base_url}/api/tables/index"
                r = requests.get(url, headers=api_headers(), timeout=15)
                st.json(r.json())
            except Exception as e:
                st.error(str(e))

        st.markdown("**Loaded categories:**")
        st.write(f"{len(st.session_state.categories)} categories")
        st.markdown("**Loaded dishes:**")
        for k, v in st.session_state.dishes.items():
            st.write(f"Category {k}: {len(v)} dishes")
        st.markdown("**Loaded tables:**")
        st.write(f"{len(st.session_state.tables)} tables")


# ─── Header ───
st.markdown("""
<div class="main-header">
    <h1>⚡ POS Order Automation</h1>
    <p>Al-Kout Restaurant • مطعم الكوت</p>
</div>
""", unsafe_allow_html=True)

# ─── Main Tabs ───
tab_create, tab_history = st.tabs(["📋 Create Orders", "📜 Order History & Recreate"])


# ═══════════════════════════════════════════
# TAB 1: CREATE ORDERS
# ═══════════════════════════════════════════
with tab_create:
    if not st.session_state.connected:
        st.warning("👈 Connect to the server first using the sidebar!")
        st.info("1. Paste your Bearer token\n2. Click **Connect & Load Menu**\n3. Start creating orders!")
    else:
        # ── Order Type ──
        st.markdown("### Order Configuration")

        col_type, col_pay = st.columns(2)
        with col_type:
            order_type = st.selectbox(
                "📋 Order Type",
                ["takeaway", "dine-in", "delivery", "talabat"],
                format_func=lambda x: {
                    "dine-in": "🪑 في المطعم (Dine-in)",
                    "takeaway": "📦 إستلام (Takeaway)",
                    "delivery": "🛵 توصيل (Delivery)",
                    "talabat": "📱 طلبات (Talabat)",
                }[x]
            )

        with col_pay:
            payment = st.selectbox(
                "💳 Payment",
                ["unpaid", "cash", "visa", "cash_visa"],
                format_func=lambda x: {
                    "unpaid": "⏳ غير مدفوع (Unpaid)",
                    "cash": "💵 كاش (Cash)",
                    "visa": "💳 فيزا (Visa)",
                    "cash_visa": "💵💳 كاش + فيزا (Cash+Visa)",
                }[x]
            )

        # ── Type-specific fields ──
        table_id = None
        delivery_info = {}
        reference = ""
        cash_amount = 0

        if order_type == "dine-in":
            st.markdown("#### 🪑 Table Selection")
            tables = st.session_state.tables
            if tables:
                # Separate available and occupied using is_available flag set during fetch
                available = [t for t in tables if t.get("is_available", False)]
                occupied = [t for t in tables if not t.get("is_available", False)]

                # Show filter
                show_all = st.checkbox("Show all tables (including occupied)", value=False)
                display_tables = tables if show_all else (available if available else tables)

                if display_tables:
                    table_options = {}
                    for t in display_tables:
                        status_icon = "🟢" if t in available else "🔴"
                        zone_text = f" — {t['zone']}" if t.get("zone") else ""
                        status_text = f" ({t['status']})" if t.get("status") else ""
                        table_options[t["id"]] = f"{status_icon} {t['name']}{zone_text}{status_text}"

                    table_id = st.selectbox(
                        "🪑 Choose Table",
                        list(table_options.keys()),
                        format_func=lambda x: table_options.get(x, str(x))
                    )

                    if available:
                        st.caption(f"🟢 {len(available)} available | 🔴 {len(occupied)} occupied")
                    else:
                        st.warning("⚠ No available tables found — showing all tables")
                else:
                    st.warning("No tables found")
                    table_id = st.number_input("Table Number (manual)", min_value=1, max_value=200, value=40)
            else:
                st.info("Tables not loaded. Click 'Connect & Load Menu' first.")
                table_id = st.number_input("Table Number (manual)", min_value=1, max_value=200, value=40)

        if order_type == "delivery":
            st.markdown("#### 🛵 Delivery Information")
            dc1, dc2 = st.columns(2)
            with dc1:
                del_client_name = st.text_input("👤 Client Name", placeholder="أحمد محمد")
            with dc2:
                del_country_code = st.text_input("🌍 Country Code", value="20", help="20 = Egypt")

            dc3, dc4 = st.columns(2)
            with dc3:
                del_phone = st.text_input("📞 Phone (without country code)", placeholder="1019242992")
            with dc4:
                del_addr_type = st.selectbox("🏠 Address Type", ["شقة", "فيلا", "مكتب", "فندق"])

            # Area selection from API
            areas = st.session_state.areas
            del_area_id = None
            if areas:
                area_options = {a["id"]: a["name"] for a in areas}
                del_area_id = st.selectbox(
                    "📍 Delivery Area",
                    list(area_options.keys()),
                    format_func=lambda x: area_options.get(x, str(x))
                )
            else:
                st.warning("⚠ No areas loaded — reconnect to load delivery areas")
                del_area_id = st.number_input("Area ID (manual)", min_value=1, value=1)

            del_address = st.text_input("📍 Street Address", placeholder="٥ شارع النصر")

            del_building = del_floor = del_apartment = del_notes = ""
            with st.expander("➕ Optional Details (building, floor, apartment, notes)"):
                dopt1, dopt2, dopt3 = st.columns(3)
                with dopt1:
                    del_building = st.text_input("🏢 Building", placeholder="مبنى 5")
                with dopt2:
                    del_floor = st.text_input("📶 Floor", placeholder="3")
                with dopt3:
                    del_apartment = st.text_input("🚪 Apartment", placeholder="10")
                del_notes = st.text_input("📝 Notes", placeholder="أمام المسجد")

            delivery_info = {
                "client_name": del_client_name,
                "country_code": del_country_code,
                "phone": del_phone,
                "addr_type": del_addr_type,
                "area_id": del_area_id,
                "address": del_address,
                "building": del_building,
                "floor": del_floor,
                "apartment": del_apartment,
                "notes": del_notes,
            }

        if payment == "visa":
            reference = st.text_input("🔢 Visa Reference Number", placeholder="REF123456")

        if payment == "cash_visa":
            pc1, pc2 = st.columns(2)
            with pc1:
                cash_amount = st.number_input("💵 Cash Amount", min_value=0.0, value=200.0, step=10.0)
            with pc2:
                reference = st.text_input("🔢 Reference Number", placeholder="REF123456")

        # ── Items Selection ──
        st.markdown("### 🍽 Select Items")

        if "current_items" not in st.session_state:
            st.session_state.current_items = []

        # Category & dish selector
        categories = st.session_state.categories
        if categories:
            cat_names = {}
            for cat in categories:
                if isinstance(cat, dict):
                    cid = cat.get("id")
                    cname = cat.get("name") or cat.get("name_ar") or cat.get("title") or f"Category {cid}"
                    if cid is not None:
                        cat_names[cid] = cname

            if not cat_names:
                st.warning("No valid categories found. Check the Debug section in sidebar.")
            else:
                sel_col1, sel_col2, sel_col3, sel_col4 = st.columns([3, 3, 1, 1])

                with sel_col1:
                    selected_cat_id = st.selectbox(
                        "📂 Category",
                        list(cat_names.keys()),
                        format_func=lambda x: cat_names.get(x, str(x))
                    )

                # Get dishes for selected category
                cat_dishes = st.session_state.dishes.get(selected_cat_id, [])

                with sel_col2:
                    selected_dish_id = None
                    if cat_dishes:
                        dish_options = {}
                        for d in cat_dishes:
                            if not isinstance(d, dict):
                                continue
                            did = d.get("id") or d.get("dish_id")
                            dname = d.get("name") or d.get("dish_name", "Unknown")
                            dprice = d.get("price") or d.get("dish_price", 0)
                            if did is not None:
                                dish_options[did] = (dname, dprice)

                        # Detect duplicate names and append ID to distinguish them
                        name_counts = {}
                        for label, price in dish_options.values():
                            name_counts[label] = name_counts.get(label, 0) + 1
                        dish_options = {
                            did: f"{lbl} — {prc} ج.م{f' (#{did})' if name_counts[lbl] > 1 else ''}"
                            for did, (lbl, prc) in dish_options.items()
                        }

                        if dish_options:
                            selected_dish_id = st.selectbox(
                                "🍽 Dish",
                                list(dish_options.keys()),
                                format_func=lambda x: dish_options.get(x, str(x))
                            )
                        else:
                            st.warning("No valid dishes found")
                    else:
                        st.info("No dishes in this category")

                with sel_col3:
                    item_qty = st.number_input("Qty", min_value=1, max_value=99, value=1, key="add_qty")

                with sel_col4:
                    st.markdown("<br>", unsafe_allow_html=True)
                    add_clicked = st.button("➕ Add", use_container_width=True, type="primary")

                # Item note & addons
                item_note = st.text_input("📝 Item Note (optional)", placeholder="e.g. No onions, extra spicy...", key="item_note_input")

                # Handle addons for selected dish
                selected_addons = []
                selected_size_id = None
                selected_size_name = ""

                if selected_dish_id and cat_dishes:
                    dish_data = next((d for d in cat_dishes if isinstance(d, dict) and (d.get("id") or d.get("dish_id")) == selected_dish_id), None)
                    if dish_data:
                        # Check for sizes
                        sizes = dish_data.get("sizes") or dish_data.get("dish_sizes", [])
                        if sizes and isinstance(sizes, list) and len(sizes) > 0:
                            size_options = {}
                            for s in sizes:
                                if isinstance(s, dict) and s.get("id"):
                                    size_options[s["id"]] = f"{s.get('name', '')} — {s.get('price', '')} ج.م"
                            if size_options:
                                selected_size_id = st.selectbox("📏 Size", list(size_options.keys()),
                                                                format_func=lambda x: size_options.get(x, str(x)))
                                size_obj = next((s for s in sizes if isinstance(s, dict) and s.get("id") == selected_size_id), None)
                                if size_obj:
                                    selected_size_name = size_obj.get("name", "")

                        # Check for addon categories
                        addon_cats = dish_data.get("addon_categories") or dish_data.get("addons", [])
                        if addon_cats and isinstance(addon_cats, list):
                            st.markdown("**🔧 Addons:**")
                            for acat in addon_cats:
                                if not isinstance(acat, dict):
                                    continue
                                addons = acat.get("addons") or acat.get("items", [])
                                if not isinstance(addons, list):
                                    continue
                                for addon in addons:
                                    if not isinstance(addon, dict):
                                        continue
                                    aid = addon.get("id")
                                    aname = addon.get("name", "Addon")
                                    aprice = addon.get("price", 0)
                                    if aid and st.checkbox(f"{aname} (+{aprice} ج.م)", key=f"addon_{aid}"):
                                        selected_addons.append({"id": aid, "name": aname, "price": float(aprice), "category_id": acat.get("id", 1)})

                # Add item to list
                if add_clicked and selected_dish_id and cat_dishes:
                    dish_data = next((d for d in cat_dishes if isinstance(d, dict) and (d.get("id") or d.get("dish_id")) == selected_dish_id), None)
                    if dish_data:
                        built_item = build_item(
                            dish_data, item_qty, item_note,
                            selected_addons, selected_size_id, selected_size_name
                        )
                        built_item["_dish_data"] = dish_data
                        built_item["_addons"] = selected_addons
                        st.session_state.current_items.append(built_item)
                        st.rerun()

        # ── Current Items List ──
        if st.session_state.current_items:
            st.markdown("### 🛒 Cart")
            total_price = 0
            items_to_remove = []

            for idx, item in enumerate(st.session_state.current_items):
                ic1, ic2, ic3, ic4 = st.columns([4, 1, 1, 1])
                with ic1:
                    addon_text = ""
                    if item.get("selectedAddons"):
                        addon_names = [a["name"] for a in item["selectedAddons"]]
                        addon_text = f" + {', '.join(addon_names)}"
                    size_text = f" ({item['sizeName']})" if item.get("sizeName") else ""
                    note_text = f" 📝 {item['note']}" if item.get("note") else ""
                    st.markdown(f"**{item['dish_name']}**{size_text}{addon_text}{note_text}")
                with ic2:
                    st.markdown(f"×{item['quantity']}")
                with ic3:
                    st.markdown(f"**{item['finalPrice']} ج.م**")
                with ic4:
                    if st.button("🗑", key=f"remove_{idx}"):
                        items_to_remove.append(idx)

                total_price += item["finalPrice"]

            # Remove items
            for idx in sorted(items_to_remove, reverse=True):
                st.session_state.current_items.pop(idx)
            if items_to_remove:
                st.rerun()

            # Totals
            tax = round(total_price * 0.14, 2)
            grand_total = round(total_price + tax, 2)
            st.divider()
            tc1, tc2, tc3 = st.columns(3)
            with tc1:
                st.metric("Subtotal", f"{total_price} ج.م")
            with tc2:
                st.metric("VAT (14%)", f"{tax} ج.م")
            with tc3:
                st.metric("Total", f"{grand_total} ج.م")

        # ── Cash Amount & Tip Options (for paid orders) ──
        paid_amount = 0
        tip_option = "no_tip"
        tip_amount = 0

        if payment in ("cash", "cash_visa") and st.session_state.current_items:
            # Calculate totals
            _sub = sum(i["finalPrice"] for i in st.session_state.current_items)
            _tax = round(_sub * 0.14, 2)
            _bill = round(_sub + _tax, 2)

            # Round options
            round_50 = int((_bill // 50 + 1) * 50) if _bill % 50 != 0 else int(_bill)
            round_100 = int((_bill // 100 + 1) * 100) if _bill % 100 != 0 else int(_bill)

            st.markdown("### 💰 Cash Payment Amount")

            amount_option = st.radio(
                "Choose amount",
                ["exact", "round_50", "round_100", "custom"],
                format_func=lambda x: {
                    "exact": f"💰 المبلغ المستحق — {_bill} ج.م",
                    "round_50": f"🔄 أقرب 50 — {round_50} ج.م",
                    "round_100": f"🔄 أقرب 100 — {round_100} ج.م",
                    "custom": "✏️ مبلغ مخصص",
                }[x],
                horizontal=True,
            )

            if amount_option == "exact":
                paid_amount = _bill
            elif amount_option == "round_50":
                paid_amount = round_50
            elif amount_option == "round_100":
                paid_amount = round_100
            else:
                paid_amount = st.number_input("أدخل المبلغ المدفوع", min_value=0.0, value=float(_bill), step=10.0)

            # Change calculation
            change = round(paid_amount - _bill, 2)
            if change > 0:
                st.info(f"💰 الباقي المحتمل (قبل الإكرامية): **{change} ج.م**")

                # Tip options
                st.markdown("### 🎁 إكرامية (Tip)")
                tip_option = st.radio(
                    "خيارات الإكرامية",
                    ["no_tip", "tip_the_change", "tip_specific"],
                    format_func=lambda x: {
                        "no_tip": f"❌ بدون إكرامية — رد {change} ج.م",
                        "tip_the_change": f"💚 الباقي كله — إكرامية {change} ج.م",
                        "tip_specific": "✏️ مبلغ محدد",
                    }[x],
                    horizontal=True,
                )

                if tip_option == "tip_the_change":
                    tip_amount = change
                elif tip_option == "tip_specific":
                    tip_amount = st.number_input("مبلغ الإكرامية", min_value=0.0, max_value=float(change), value=0.0, step=1.0)
                    tip_option = "tip_specific_amount"

                approved_tip = tip_amount
                returned = round(change - approved_tip, 2)
                st.success(f"✅ الإكرامية المعتمدة: **{approved_tip} ج.م** | المتبقي للرد: **{returned} ج.م**")
            else:
                change = 0

        elif payment == "visa" and st.session_state.current_items:
            _sub = sum(i["finalPrice"] for i in st.session_state.current_items)
            _tax = round(_sub * 0.14, 2)
            _bill = round(_sub + _tax, 2)
            paid_amount = _bill
            change = 0

        # ── Order Note ──
        order_note = st.text_area("📝 Order Note", placeholder="Optional note for the entire order...", height=68)

        # ── Number of copies ──
        st.markdown("### 🔄 Order Copies")
        num_copies = st.slider("How many copies of this order?", min_value=1, max_value=20, value=1)

        # ── Submit ──
        st.divider()
        if st.button(f"🚀 Create {num_copies} Order{'s' if num_copies > 1 else ''}", use_container_width=True, type="primary",
                      disabled=len(st.session_state.current_items) == 0):

            if not st.session_state.current_items:
                st.error("Add at least one item!")
            else:
                # Build order config
                # Resolve table name for dine-in
                _table_name = None
                if table_id is not None:
                    _tbl = next((t for t in st.session_state.tables if t["id"] == table_id), None)
                    _table_name = _tbl["name"] if _tbl else str(table_id)

                order_config = {
                    "type": order_type,
                    "payment": payment,
                    "table_id": table_id,
                    "table_name": _table_name,
                    "note": order_note,
                    "reference": reference,
                    "cash_amount": cash_amount,
                    "paid_amount": paid_amount,
                    "tip_option": tip_option,
                    "tip_amount": tip_amount,
                    "delivery": delivery_info,
                    "items": [
                        {k: v for k, v in item.items() if not k.startswith("_")}
                        for item in st.session_state.current_items
                    ],
                    # Store full items for recreate
                    "_full_items": st.session_state.current_items.copy(),
                }

                # For delivery orders: create the address ONCE, reuse address_id for all copies
                if order_type == "delivery":
                    addr_placeholder = st.empty()
                    addr_placeholder.info("📍 Creating delivery address...")
                    address_id, addr_err = create_delivery_address(delivery_info)
                    if addr_err:
                        st.error(f"❌ Failed to create delivery address: {addr_err}")
                        st.stop()
                    order_config["address_id"] = address_id
                    addr_placeholder.success(f"✅ Address created (ID: {address_id})")

                # For dine-in with multiple copies, build a pool of available tables
                # starting with the selected table, then the rest of available tables
                dine_in_table_pool = []
                if order_type == "dine-in" and num_copies > 1:
                    available_tables = [t for t in st.session_state.tables if t.get("is_available", False)]
                    selected_first = [t for t in available_tables if t["id"] == table_id]
                    rest = [t for t in available_tables if t["id"] != table_id]
                    dine_in_table_pool = selected_first + rest

                progress = st.progress(0)
                status = st.empty()

                results = []
                for i in range(num_copies):
                    status.markdown(f"⏳ Creating order {i+1}/{num_copies}...")
                    if dine_in_table_pool:
                        if i < len(dine_in_table_pool):
                            t = dine_in_table_pool[i]
                            order_config["table_id"] = t["id"]
                            order_config["table_name"] = t["name"]
                        else:
                            results.append({"success": False, "error": "No more available tables", "bill": 0, "order_id": None, "invoice_id": None, "raw": None})
                            progress.progress((i + 1) / num_copies)
                            continue
                    result = send_order(order_config)
                    results.append(result)

                    # Save to history
                    st.session_state.orders_history.append({
                        "config": order_config,
                        "result": result,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "copy": i + 1,
                    })

                    progress.progress((i + 1) / num_copies)

                    if i < num_copies - 1:
                        time.sleep(0.8)

                # Show results
                success_count = sum(1 for r in results if r["success"])
                if success_count == num_copies:
                    status.success(f"✅ All {num_copies} orders created successfully!")
                elif success_count > 0:
                    status.warning(f"⚠️ {success_count}/{num_copies} orders created")
                else:
                    status.error(f"❌ All orders failed")

                for i, r in enumerate(results):
                    if r["success"]:
                        st.markdown(f"""
                        <div class="result-success">
                            <strong>✅ Order #{i+1}</strong> — {r['bill']} ج.م<br>
                            <small>Order ID: <code>{r['order_id']}</code></small><br>
                            <small>Invoice: <code>{r['invoice_id']}</code></small>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        err_msg = r.get("error", "Unknown error")
                        with st.expander(f"❌ Order #{i+1} — failed (click to expand)", expanded=True):
                            st.error(err_msg)
                            if r.get("raw"):
                                st.json(r["raw"])


# ═══════════════════════════════════════════
# TAB 2: ORDER HISTORY & RECREATE
# ═══════════════════════════════════════════
with tab_history:
    if not st.session_state.orders_history:
        st.info("No orders yet. Create some orders first!")
    else:
        st.markdown(f"### 📜 Order History ({len(st.session_state.orders_history)} orders)")

        # Summary stats
        sc1, sc2, sc3, sc4 = st.columns(4)
        all_orders = st.session_state.orders_history
        with sc1:
            st.metric("Total", len(all_orders))
        with sc2:
            st.metric("✅ Success", sum(1 for o in all_orders if o["result"].get("success")))
        with sc3:
            st.metric("❌ Failed", sum(1 for o in all_orders if not o["result"].get("success")))
        with sc4:
            total_revenue = sum(o["result"].get("bill", 0) for o in all_orders if o["result"].get("success"))
            st.metric("💰 Total Revenue", f"{total_revenue} ج.م")

        st.divider()

        # Order list (newest first)
        for idx, order in enumerate(reversed(all_orders)):
            real_idx = len(all_orders) - 1 - idx
            config = order["config"]
            result = order["result"]
            ts = order["timestamp"]

            type_labels = {
                "dine-in": "🪑 في المطعم",
                "takeaway": "📦 إستلام",
                "delivery": "🛵 توصيل",
                "talabat": "📱 طلبات",
            }
            pay_labels = {
                "unpaid": "⏳ غير مدفوع",
                "cash": "💵 كاش",
                "visa": "💳 فيزا",
                "cash_visa": "💵💳 كاش+فيزا",
            }

            status_icon = "✅" if result.get("success") else "❌"
            type_label = type_labels.get(config["type"], config["type"])
            pay_label = pay_labels.get(config["payment"], config["payment"])
            bill = result.get("bill", 0)
            items_count = len(config.get("items", []))

            with st.expander(f"{status_icon} {type_label} — {pay_label} — {bill} ج.م — {ts}", expanded=False):

                # Order details
                dc1, dc2, dc3 = st.columns(3)
                with dc1:
                    st.markdown(f"**Type:** {type_label}")
                    st.markdown(f"**Payment:** {pay_label}")
                with dc2:
                    st.markdown(f"**Bill:** {bill} ج.م")
                    st.markdown(f"**Items:** {items_count}")
                with dc3:
                    st.markdown(f"**Time:** {ts}")
                    if config.get("note"):
                        st.markdown(f"**Note:** {config['note']}")

                # Show items
                st.markdown("**Items:**")
                for item in config.get("items", []):
                    addon_text = ""
                    if item.get("selectedAddons"):
                        addon_text = " + " + ", ".join(a["name"] for a in item["selectedAddons"])
                    st.markdown(f"- {item.get('dish_name', 'Unknown')} ×{item.get('quantity', 1)} = {item.get('finalPrice', 0)} ج.م{addon_text}")

                # Result
                if result.get("success"):
                    st.code(f"Order ID:   {result['order_id']}\nInvoice ID: {result['invoice_id']}", language="text")
                else:
                    st.error(result.get("error", "Failed"))

                # ── RECREATE BUTTON ──
                st.divider()
                rec_col1, rec_col2 = st.columns([1, 3])
                with rec_col1:
                    recreate_count = st.number_input("Copies", min_value=1, max_value=50, value=1, key=f"rec_count_{real_idx}")
                with rec_col2:
                    if st.button(f"🔄 Recreate {recreate_count}x", key=f"recreate_{real_idx}", type="primary", use_container_width=True):
                        recreate_progress = st.progress(0)
                        recreate_status = st.empty()
                        recreate_results = []

                        for i in range(recreate_count):
                            recreate_status.markdown(f"⏳ Recreating {i+1}/{recreate_count}...")
                            # Use the same config
                            r = send_order(config)
                            recreate_results.append(r)

                            st.session_state.orders_history.append({
                                "config": config,
                                "result": r,
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "copy": i + 1,
                            })

                            recreate_progress.progress((i + 1) / recreate_count)
                            if i < recreate_count - 1:
                                time.sleep(0.8)

                        rec_success = sum(1 for r in recreate_results if r["success"])
                        if rec_success == recreate_count:
                            recreate_status.success(f"✅ Recreated {recreate_count}x successfully!")
                        else:
                            recreate_status.warning(f"⚠️ {rec_success}/{recreate_count} recreated")

                        for i, r in enumerate(recreate_results):
                            if r["success"]:
                                st.markdown(f"✅ **#{i+1}** Order: `{r['order_id']}` Invoice: `{r['invoice_id']}`")
                            else:
                                st.markdown(f"❌ **#{i+1}** {r.get('error', 'Failed')}")

        # Clear history
        st.divider()
        if st.button("🗑 Clear History", type="secondary"):
            st.session_state.orders_history = []
            st.rerun()

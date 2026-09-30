import streamlit as st
from supabase import create_client, Client
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import uuid

# --- INIT SUPABASE ---
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase: Client = init_connection()

# --- SESSION STATE ---
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'username' not in st.session_state:
    st.session_state.username = None

# --- AUTHENTICATION ---
def login():
    with st.sidebar.form("login_form"):
        st.subheader("Admin Login")
        user = st.text_input("Username")
        pwd = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            res = supabase.table("users").select("*").eq("username", user).execute()
            if res.data and check_password_hash(res.data[0]['password_hash'], pwd):
                st.session_state.user_id = res.data[0]['id']
                st.session_state.username = user
                st.success("Logged in successfully!")
                st.rerun()
            else:
                st.error("Invalid credentials")

def logout():
    st.session_state.user_id = None
    st.session_state.username = None
    st.rerun()

@st.dialog("Change Password")
def change_password_dialog():
    new_pwd = st.text_input("New Password", type="password")
    if st.button("Update Password"):
        if len(new_pwd) < 4:
            st.error("Password too short.")
        else:
            new_hash = generate_password_hash(new_pwd)
            supabase.table("users").update({"password_hash": new_hash}).eq("id", st.session_state.user_id).execute()
            st.success("Password updated!")
            st.rerun()

# --- HELPER FUNCTIONS ---
def fetch_data(table, join=None, eq_filter=None, neq_filter=None):
    query = supabase.table(table).select(join if join else "*")
    if eq_filter:
        query = query.eq(eq_filter[0], eq_filter[1])
    if neq_filter:
        query = query.neq(neq_filter[0], neq_filter[1])
    return query.execute().data

# --- DIALOGS (MODALS) FOR ADDING/EDITING ---
@st.dialog("Add / Edit Wrap")
def wrap_dialog(wrap=None):
    st.write("Leave photo blank to keep existing photo" if wrap else "Upload wrap photo")
    name = st.text_input("Name", value=wrap['name'] if wrap else "")
    color = st.text_input("Color", value=wrap['color'] if wrap else "")
    price = st.number_input("Price per m² ($)", min_value=0.1, value=float(wrap['price_per_sqm']) if wrap else 50.0)
    photo = st.file_uploader("Wrap Photo", type=["jpg", "jpeg", "png"])
    
    if st.button("Save Wrap"):
        if not name or not color:
            st.error("Name and color are required.")
            return
            
        photo_url = wrap['photo_url'] if wrap else ""
        if photo:
            # Upload to Supabase Storage
            file_ext = photo.name.split('.')[-1]
            file_name = f"{uuid.uuid4()}.{file_ext}"
            supabase.storage.from_("wraps").upload(file_name, photo.getvalue())
            photo_url = supabase.storage.from_("wraps").get_public_url(file_name)
            
        data = {"name": name, "color": color, "price_per_sqm": price, "photo_url": photo_url}
        if wrap:
            supabase.table("wraps").update(data).eq("id", wrap['id']).execute()
        else:
            supabase.table("wraps").insert(data).execute()
        st.success("Saved!")
        st.rerun()

@st.dialog("Add / Edit Customer")
def customer_dialog(customer=None):
    name = st.text_input("Name*", value=customer['name'] if customer else "")
    email = st.text_input("Email", value=customer['email'] if customer else "")
    phone = st.text_input("Phone*", value=customer['phone'] if customer else "")
    brand = st.text_input("Car Brand*", value=customer['car_brand'] if customer else "")
    model = st.text_input("Car Model*", value=customer['car_model'] if customer else "")
    year = st.number_input("Car Year*", min_value=1900, max_value=2100, step=1, value=int(customer['car_year']) if customer else 2020)
    req = st.text_area("Special Request", value=customer['request'] if customer else "")
    
    if st.button("Save Customer"):
        if not name or not phone or not brand or not model:
            st.error("Please fill in all required (*) fields.")
            return
        data = {"name": name, "email": email, "phone": phone, "car_brand": brand, "car_model": model, "car_year": year, "request": req}
        if customer:
            supabase.table("customers").update(data).eq("id", customer['id']).execute()
        else:
            supabase.table("customers").insert(data).execute()
        st.success("Saved!")
        st.rerun()

@st.dialog("Add / Edit Project")
def project_dialog(project=None):
    customers = fetch_data("customers")
    wraps = fetch_data("wraps")
    
    if not customers or not wraps:
        st.warning("Please add at least one customer and one wrap before creating a project.")
        return

    # Mappings for selectboxes
    cust_options = {f"{c['name']} - {c['car_brand']} {c['car_model']}": c['id'] for c in customers}
    wrap_options = {f"{w['name']} (${w['price_per_sqm']}/m²)": w for w in wraps}

    # Defaults
    def_cust = list(cust_options.keys())[0]
    def_wrap = list(wrap_options.keys())[0]
    if project:
        def_cust = next((k for k, v in cust_options.items() if v == project['customer_id']), def_cust)
        def_wrap = next((k for k, v in wrap_options.items() if v['id'] == project['wrap_id']), def_wrap)

    sel_cust = st.selectbox("Customer", options=list(cust_options.keys()), index=list(cust_options.keys()).index(def_cust))
    sel_wrap = st.selectbox("Wrap", options=list(wrap_options.keys()), index=list(wrap_options.keys()).index(def_wrap))
    sqm = st.number_input("Square Meters", min_value=0.1, value=float(project['sqm']) if project else 10.0, step=0.5)
    
    # Auto-calculate price
    chosen_wrap = wrap_options[sel_wrap]
    calc_price = sqm * chosen_wrap['price_per_sqm']
    st.info(f"**Calculated Total Price:** ${calc_price:,.2f}")
    
    start_date = st.date_input("Start Date", value=pd.to_datetime(project['start_date']) if project else "today")
    deadline = st.date_input("Deadline", value=pd.to_datetime(project['deadline']) if project else "today")
    
    statuses = ["In process", "Future order", "Done", "Complications"]
    status = st.selectbox("Status", statuses, index=statuses.index(project['status']) if project else 0)

    if st.button("Save Project"):
        data = {
            "customer_id": cust_options[sel_cust], "wrap_id": chosen_wrap['id'],
            "sqm": sqm, "price": calc_price, 
            "start_date": start_date.strftime("%Y-%m-%d"), "deadline": deadline.strftime("%Y-%m-%d"), 
            "status": status
        }
        if project:
            supabase.table("projects").update(data).eq("id", project['id']).execute()
        else:
            supabase.table("projects").insert(data).execute()
        st.success("Saved!")
        st.rerun()

@st.dialog("Client Details")
def client_details_dialog(proj):
    st.subheader(f"Project for {proj['customers']['name']}")
    st.write(f"**Email:** {proj['customers']['email']}")
    st.write(f"**Phone:** {proj['customers']['phone']}")
    st.write(f"**Car:** {proj['customers']['car_brand']} {proj['customers']['car_model']} ({proj['customers']['car_year']})")
    st.write(f"**Request:** {proj['customers']['request']}")
    st.divider()
    st.write(f"**Wrap Chosen:** {proj['wraps']['name']} ({proj['wraps']['color']})")
    st.write(f"**Amount Needed:** {proj['sqm']} m²")
    st.write(f"**Total Price:** ${proj['price']:,.2f}")
    st.write(f"**Timeline:** {proj['start_date']} to {proj['deadline']}")
    st.write(f"**Status:** {proj['status']}")

# --- MAIN UI ---
st.set_page_config(page_title="Car Wrap Manager", layout="wide")

# Sidebar Navigation & Auth
st.sidebar.title("WrapManager")
menu = st.sidebar.radio("Navigation", ["Active Projects", "Past Projects", "Customers", "Wrap Catalog"])

if not st.session_state.user_id:
    login()
else:
    st.sidebar.success(f"Logged in as Admin")
    if st.sidebar.button("Change Password"):
        change_password_dialog()
    if st.sidebar.button("Logout"):
        logout()

st.title(menu)

if menu in ["Active Projects", "Past Projects"]:
    is_past = (menu == "Past Projects")
    
    if not is_past and st.session_state.user_id:
        if st.button("➕ New Project", type="primary"):
            project_dialog()
            
    # Fetch projects with joined tables
    filter_condition = ("status", "Done") if is_past else None
    projects = supabase.table("projects").select("*, customers(*), wraps(*)").eq("status", "Done").execute().data if is_past else \
               supabase.table("projects").select("*, customers(*), wraps(*)").neq("status", "Done").execute().data
               
    if projects:
        for p in projects:
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
                with col1:
                    st.write(f"**{p['customers']['name']}**")
                    st.caption(f"{p['customers']['car_brand']} {p['customers']['car_model']}")
                with col2:
                    st.write(f"Wrap: {p['wraps']['name']}")
                    st.caption(f"{p['sqm']} m² | ${p['price']:,.2f}")
                with col3:
                    st.write(f"Status: {p['status']}")
                    st.caption(f"Due: {p['deadline']}")
                with col4:
                    if st.button("Details", key=f"det_{p['id']}"):
                        client_details_dialog(p)
                    if st.session_state.user_id:
                        if st.button("Edit", key=f"ed_{p['id']}"):
                            project_dialog(p)
    else:
        st.info("No projects found.")

elif menu == "Wrap Catalog":
    if st.session_state.user_id:
        if st.button("➕ Add Wrap", type="primary"):
            wrap_dialog()
            
    wraps = fetch_data("wraps")
    if wraps:
        cols = st.columns(3)
        for i, w in enumerate(wraps):
            with cols[i % 3]:
                st.container(border=True)
                if w.get('photo_url'):
                    st.image(w['photo_url'], use_column_width=True)
                else:
                    st.write("*(No Image)*")
                st.subheader(w['name'])
                st.write(f"**Color:** {w['color']}")
                st.write(f"**Price/m²:** ${w['price_per_sqm']}")
                if st.session_state.user_id:
                    if st.button("Edit", key=f"w_ed_{w['id']}"):
                        wrap_dialog(w)
    else:
        st.info("No wraps in catalog.")

elif menu == "Customers":
    if st.session_state.user_id:
        if st.button("➕ Add Customer", type="primary"):
            customer_dialog()
            
    customers = fetch_data("customers")
    if customers:
        df = pd.DataFrame(customers)
        # Drop ID and reorganize for display
        display_df = df[['name', 'phone', 'email', 'car_brand', 'car_model', 'car_year', 'request']]
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        if st.session_state.user_id:
            st.write("### Edit a Customer")
            cust_to_edit = st.selectbox("Select customer to edit", options=[c['name'] for c in customers])
            if st.button("Edit Selected Customer"):
                selected = next(c for c in customers if c['name'] == cust_to_edit)
                customer_dialog(selected)
    else:
        st.info("No customers found.")
        
if st.sidebar.button("Fix Password"):
    new_hash = generate_password_hash("admin")
    supabase.table("users").update({"password_hash": new_hash}).eq("username", "admin").execute()
    st.sidebar.success("Database fixed! You can now log in with admin / admin")

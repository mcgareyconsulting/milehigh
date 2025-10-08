import requests
import pandas as pd
from io import BytesIO
from app.config import Config as cfg
from openpyxl import load_workbook


relevant_columns = [
    "Job #",
    "Release #",
    "Job",
    "Description",
    "Fab Hrs",
    "Install HRS",
    "Paint color",
    "PM",
    "BY",
    "Released",
    "Fab Order",
    "Cut start",
    "Fitup comp",
    "Welded",
    "Paint Comp",
    "Ship",
    "Start install",
    "Comp. ETA",
    "Job Comp",
    "Invoiced",
    "Notes",
]


def get_access_token():
    """
    Get an access token for Microsoft Graph API using client credentials.
    """
    url = f"https://login.microsoftonline.com/{cfg.AZURE_TENANT_ID}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": cfg.AZURE_CLIENT_ID,
        "client_secret": cfg.AZURE_CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
    }
    r = requests.post(url, data=data)
    r.raise_for_status()
    return r.json()["access_token"]


def get_excel_dataframe():
    token = get_access_token()
    file_bytes = read_file_from_user_onedrive(
        token, cfg.ONEDRIVE_USER_EMAIL, cfg.ONEDRIVE_FILE_PATH
    )

    usecols = list(range(0, 17))
    sheet_name = "Job Log"  

    df_all = pd.read_excel(
        BytesIO(file_bytes), header=2, usecols=usecols, sheet_name=sheet_name
    )

    # First data row is Excel row 4; store it before filtering
    df_all = df_all.reset_index(drop=False).rename(columns={"index": "_row0"})
    df_all["_excel_row"] = df_all["_row0"] + 4

    df_final = df_all.dropna(subset=["Job #", "Release #"]).copy()

    wb = load_workbook(BytesIO(file_bytes), data_only=False)
    ws = wb[sheet_name]

    formula_col = 17  # Q
    formulas, has_formula = [], []

    for r in df_final["_excel_row"]:
        cell = ws.cell(row=int(r), column=formula_col)
        val = cell.value
        is_formula = isinstance(val, str) and val.startswith("=")
        formulas.append(val if is_formula else "")
        has_formula.append(is_formula)

    df_final["start_install_formula"] = formulas
    df_final["start_install_formulaTF"] = has_formula

    # Tidy up helper cols
    df_final = df_final.drop(columns=["_row0", "_excel_row"]).reset_index(drop=True)
    return df_final


def get_last_modified_time():
    access_token = get_access_token()
    file_path = cfg.ONEDRIVE_FILE_PATH  # e.g. "/Job Log 2.4 DM play toy (1).xlsm"
    user_email = cfg.ONEDRIVE_USER_EMAIL

    url = (
        f"https://graph.microsoft.com/v1.0/users/{user_email}/drive/root:/{file_path}:"
    )

    headers = {"Authorization": f"Bearer {access_token}"}

    r = requests.get(url, headers=headers)
    r.raise_for_status()
    data = r.json()

    return {
        "name": data.get("name"),
        "id": data.get("id"),
        "lastModifiedDateTime": data.get("lastModifiedDateTime"),
        "size": data.get("size"),
    }


def get_excel_data_with_timestamp():
    """
    Get the latest Excel data from OneDrive along with the last modified time.
    Returns a dict: {"last_modified": ..., "data": DataFrame}
    """
    last_modified_info = get_last_modified_time()
    df = get_excel_dataframe()
    return {
        "name": last_modified_info.get("name"),
        "last_modified_time": last_modified_info.get("lastModifiedDateTime"),
        "data": df,
    }


def read_file_from_user_onedrive(access_token, user_email, file_path):
    url = f"https://graph.microsoft.com/v1.0/users/{user_email}/drive/root:/{file_path}:/content"
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.content


def list_root_contents(access_token, user_email):
    url = f"https://graph.microsoft.com/v1.0/users/{user_email}/drive/root/children"
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.json()


def update_excel_cell(cell_address, value, worksheet_name="Job Log"):
    """
    Update a specific Excel cell via Microsoft Graph API

    Args:
        cell_address: Excel cell address (e.g., "O155")
        value: Value to set in the cell
        worksheet_name: Name of the worksheet (default: "Sheet1")

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Get access token
        access_token = get_access_token()

        # Build the URL for updating the cell
        user_email = cfg.ONEDRIVE_USER_EMAIL
        file_path = cfg.ONEDRIVE_FILE_PATH

        # URL to update a specific cell range
        url = f"https://graph.microsoft.com/v1.0/users/{user_email}/drive/root:/{file_path}:/workbook/worksheets/{worksheet_name}/range(address='{cell_address}')"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        # Payload with the new value
        payload = {"values": [[value]]}

        print(f"Updating Excel cell {cell_address} with value: {value}")
        print(f"URL: {url}")

        # Make the PATCH request
        response = requests.patch(url, headers=headers, json=payload)

        if response.status_code == 200:
            print(f"Successfully updated cell {cell_address} with value '{value}'")
            return True
        else:
            print(f"Error updating Excel: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        print(f"Exception in update_excel_cell: {e}")
        return False

"""Admin user directory: auth gates, employee/subcontractor split, role labels."""
from tests.conftest import make_user, make_subcontractor

from app.brain.directory.routes import employee_role, split_contact_name


def test_directory_requires_auth(client):
    assert client.get("/brain/directory").status_code == 401


def test_directory_requires_admin(non_admin_client):
    assert non_admin_client.get("/brain/directory").status_code == 403


def test_directory_splits_employees_and_subcontractors(app, admin_client):
    make_user(
        "carendt@mhmw.com",
        first_name="Colton",
        last_name="Arendt",
        is_drafter=True,
    )
    make_user(
        "boneill@mhmw.com",
        first_name="Bill",
        last_name="O'Neill",
        is_admin=True,
        is_drafter=True,
    )
    make_user("khearn@mhmw.com", first_name="Katie", last_name="Hearn")
    make_subcontractor("sam@acme.test", contact_name="Sam Sub")
    make_subcontractor("solo@acme.test", contact_name="Madonna")

    resp = admin_client.get("/brain/directory")
    assert resp.status_code == 200
    body = resp.get_json()

    employees = {row["email"]: row for row in body["employees"]}
    assert employees["carendt@mhmw.com"] == {
        "id": employees["carendt@mhmw.com"]["id"],
        "first_name": "Colton",
        "last_name": "Arendt",
        "email": "carendt@mhmw.com",
        "role": "Drafter",
        "role_key": "drafter",
    }
    # Admin wins over a legacy row that also carries is_drafter.
    assert employees["boneill@mhmw.com"]["role"] == "Admin"
    assert employees["boneill@mhmw.com"]["role_key"] == "admin"
    assert employees["khearn@mhmw.com"]["role"] == "Default"

    last_names = [row["last_name"] for row in body["employees"]]
    assert last_names == sorted(last_names, key=str.lower)

    subs = {row["email"]: row for row in body["subcontractors"]}
    assert subs["sam@acme.test"]["first_name"] == "Sam"
    assert subs["sam@acme.test"]["last_name"] == "Sub"
    assert subs["sam@acme.test"]["role"] == "Subcontractor"
    assert subs["solo@acme.test"]["first_name"] == "Madonna"
    assert subs["solo@acme.test"]["last_name"] == ""


def test_directory_omits_secrets(app, admin_client):
    make_user("secret@mhmw.com", first_name="Sec", last_name="Ret", password_hash="hashed")
    make_subcontractor("hidden@acme.test")

    body = admin_client.get("/brain/directory").get_json()
    blob = str(body)
    assert "password" not in blob
    assert "hashed" not in blob
    assert "token" not in blob


def test_employee_role_labels():
    class U:
        def __init__(self, is_admin=False, is_drafter=False):
            self.is_admin = is_admin
            self.is_drafter = is_drafter

    assert employee_role(U()) == "Default"
    assert employee_role(U(is_admin=True)) == "Admin"
    assert employee_role(U(is_drafter=True)) == "Drafter"
    assert employee_role(U(is_admin=True, is_drafter=True)) == "Admin"


def test_split_contact_name():
    assert split_contact_name("Sam Sub") == ("Sam", "Sub")
    assert split_contact_name("Madonna") == ("Madonna", "")
    assert split_contact_name("Mary Ann Smith") == ("Mary", "Ann Smith")
    assert split_contact_name("  ") == ("", "")
    assert split_contact_name(None) == ("", "")

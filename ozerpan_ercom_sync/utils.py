import time
from functools import wraps

import frappe
import pymysql
from frappe import generate_hash
from frappe.utils import now


def timer(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        execution_time = (end_time - start_time) * 1000
        print(f"Function '{func.__name__}' took {execution_time:.2f} ms to execute")
        return result

    return wrapper


# TODO refactor the dependant functions and clear this.
def get_mysql_connection():
    config = frappe.conf

    try:
        # Create a connection to the MySQL database using pymysql
        connection = pymysql.connect(
            host=config["ercom_db_host"],
            database=config["ercom_db_name"],  # pymysql uses "db" instead of "database"
            user=config["ercom_db_user"],
            password=config["ercom_db_password"],
            charset="utf8mb4",  # Optional: Ensure proper encoding
            cursorclass=pymysql.cursors.DictCursor,  # Optional: Return rows as dictionaries
        )
        print("\n\n\nConnected to DB Successfully.\n\n\n")
    except pymysql.MySQLError as err:
        print(f"Error connecting to MySQL database: {err}")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

    return connection


def bulk_insert_child_rows(child_table, parenttype, parentfield, rows, extra_fields=None):
    """
    Bulk insert into a child table using raw SQL.

    Args:
        child_table (str): The child DocType name (e.g., "Operation States")
        parent_type (str): The parent DocType name (e.g., "TesDetay")
        parentfield (str): The table field in parent (e.g., "operation_states")
        rows (list of dict): Each dict must have a `parent` key, plus other required fields
        extra_fields (list): Optional extra field names to include in insert
    """

    if not rows:
        return

    fields = [
        "name",
        "parentfield",
        "parent",
        "parenttype",
        "creation",
        "owner",
        "modified",
        "modified_by",
    ]

    values = []

    if extra_fields:
        fields.extend(extra_fields)

    for i, row in enumerate(rows):
        base = {
            "name": generate_hash(),
            "parentfield": parentfield,
            "parent": row["parent"],
            "parenttype": parenttype,
            "creation": now(),
            "owner": frappe.session.user,
            "modified": now(),
            "modified_by": frappe.session.user,
        }

        if extra_fields:
            for field in extra_fields:
                base[field] = row.get(field)

        values.append(tuple(base[f] for f in fields))

    placeholders = ", ".join(["%s"] * len(values))
    fields_sql = ", ".join([f"`{f}`" for f in fields])
    sql = f"""
        INSERT INTO `tab{child_table}` ({fields_sql})
        VALUES {placeholders}
    """

    frappe.db.sql(sql, tuple(values))


def bulk_delete_child_rows(child_table, parent_field, references):
    """
    Bulk delete from a child table using raw SQL.

    Args:
            child_table (str): The child DocType name (e.g., "TesDetay Operation Status")
            parent_field (str): The field to match for deletion (e.g., "job_card_ref")
            references (list): List of values to match against parent field
    """

    if not references:
        return

    placeholders = ", ".join(["%s"] * len(references))
    sql = f"""
        DELETE FROM `tab{child_table}`
        WHERE `{parent_field}` IN ({placeholders})
    """

    frappe.db.sql(sql, tuple(references))


def bulk_update_operation_status(tesdetay_refs, job_card_refs, status):
    """
    Bulk update operation states using raw SQL

    Args:
        tesdetay_refs (list): List of tesdetay references
        job_card_refs (list): List of job card references
        status (str): Status to set
    """
    if not tesdetay_refs or not job_card_refs:
        return

    # Create pairs of tesdetay_ref and job_card_ref
    pairs = list(zip(tesdetay_refs, job_card_refs))

    # Create CASE statement conditions
    case_conditions = []
    values = []
    for tesdetay_ref, job_card_ref in pairs:
        case_conditions.append(
            "(parent = %s AND job_card_ref = %s)",
        )
        values.extend([tesdetay_ref, job_card_ref])

    where_clause = " OR ".join(case_conditions)

    sql = f"""
        UPDATE `tabTesDetay Operation Status`
        SET status = %s
        WHERE {where_clause}
    """

    values.insert(0, status)
    frappe.db.sql(sql, tuple(values))

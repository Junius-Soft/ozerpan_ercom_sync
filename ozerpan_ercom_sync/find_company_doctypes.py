import frappe


@frappe.whitelist()
def get_doctypes_with_company_field():
    """
    Returns a list of all DocTypes that have a company field
    """
    # Get all DocTypes
    doctypes = frappe.get_all("DocType", filters={"custom": 0}, pluck="name")

    doctypes_with_company = []

    for doctype in doctypes:
        try:
            # Get all fields for the DocType
            meta = frappe.get_meta(doctype)

            # Check if any field is of type Company
            for field in meta.fields:
                if field.fieldname == "company":
                    doctypes_with_company.append(
                        {
                            "doctype": doctype,
                            "is_mandatory": field.reqd,
                            "label": field.label,
                        }
                    )
                    break

        except Exception as e:
            print(f"Error processing {doctype}: {str(e)}")
            continue

    print_results(doctypes_with_company)
    return doctypes_with_company


def print_results(results):
    """
    Print the results in a formatted way
    """
    # results = get_doctypes_with_company_field()

    print(f"\nFound {len(results)} DocTypes with company field:\n")
    print("DocType | Mandatory | Label")
    print("-" * 50)

    for doc in results:
        mandatory = "Yes" if doc["is_mandatory"] else "No"
        print(f"{doc['doctype']} | {mandatory} | {doc['label']}")


if __name__ == "__main__":
    print_results()

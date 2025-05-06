def get_dashboard_data(data):
    if "non_standard_fieldnames" in data:
        data["non_standard_fieldnames"]["Capacity"] = "production_plan_ref"
    else:
        data["non_standard_fieldnames"] = {
            "Capacity": "production_plan_ref",
        }

    data["transactions"].append(
        {
            "label": "Planning",
            "items": ["Capacity"],
        }
    )

    return data

# Kaynak Köşe Temizleme

## Grouping Logic
- Group barcodes by `model` and `sanal_adet`.

## Status Flow

### "Pending"
- If there is another barcode group with the status "In Progress":
  - Change their status to "Completed".
  - If all barcodes with the same `sanal_adet` are completed:
    - Close the open time log with **1 job completed**.
  - Else:
    - Close the open time log **without job completion**.
- Change the barcode group status to **"In Progress"**.
- Start timer with the employee.
- Change `job_card` status to **"Work In Progress"**.

### "In Progress"
- Change the barcode group status to **"Completed"**.
- If all barcodes with the same `sanal_adet` are completed:
  - Close the open time log with **1 job completed**.
  - If total production quantity equals produced quantity:
    - Submit the `job_card`.
  - Else:
    - Change `job_card` status to **"On Hold"**.
- Else:
  - Close the open time log **without job completion**.
  - Change `job_card` status to **"On Hold"**.

### "Completed"
- Get the list of all related `job_cards` with the same operation (including corrective ones).
- If all `job_cards` are **"Completed"** for the current barcode group:
  - **Throw an error**: "All the related Job Cards are already completed."
- Else:
  - Get the related `job_card` (not completed one).
  - If "Pending":
    - Redo the **"Pending"** process.
  - Else:
    - Redo the **"In Progress"** process.

---

## Default Grouping Logic
- Group barcodes by `sanal_adet`.

## Status Flow

### "Pending"
- If the barcode group has another **"In Progress"** `job_card` in their `operation_states` table:
  - Go to the related job card.
  - Change barcode status to **"Completed"**.
  - If all barcodes with the same `sanal_adet` are completed:
    - Close the open time log with **1 job completed**.
    - If total production quantity equals produced quantity:
      - Submit the `job_card`.
    - Else:
      - Change `job_card` status to **"On Hold"**.
  - Else:
    - Close the open time log **without job completion**.
    - Change `job_card` status to **"On Hold"**.
- If another barcode group in the current `job_card` has status **"In Progress"**:
  - Change their status to **"Completed"**.
  - If all barcodes with the same `sanal_adet` are completed in the current `job_card`:
    - Close the open time log with **1 job completed**.
  - Else:
    - Close the open time log **without job completion**.
- Change the barcode group status to **"In Progress"**.
- Start timer with the employee.
- Change `job_card` status to **"Work In Progress"**.

### "In Progress"
- Change the barcode group status to **"Completed"**.
- If all barcodes with the same `sanal_adet` are completed:
  - Close the open time log with **1 job completed**.
  - If total production quantity equals produced quantity:
    - Submit the `job_card`.
  - Else:
    - Change `job_card` status to **"On Hold"**.
- Else:
  - Close the open time log **without job completion**.
  - Change `job_card` status to **"On Hold"**.

### "Completed"
- Get the list of all related `job_cards` with the same operation (including corrective ones).
- If all `job_cards` are **"Completed"** for the current barcode group:
  - **Throw an error**: "All the related Job Cards are already completed."
- Else:
  - Get the related `job_card` (not completed one).
  - If "Pending":
    - Redo the **"Pending"** process.
  - Else:
    - Redo the **"In Progress"** process.

---

## Kalite (Quality Control)
- Group barcodes by `sanal_adet`.

## Status Flow

### "Pending" or "Correction"
- If another barcode group in the same `job_card` has status **"In Progress"**:
  - **Throw an error**: "There is an open quality control process. You should finish the open process before starting a new one."
- If the barcode group has another **"In Progress"** `job_card` in their `operation_states` table:
  - Go to the related job card.
  - Change barcode status to **"Completed"**.
  - If all barcodes with the same `sanal_adet` are completed:
    - Close the open time log with **1 job completed**.
    - If total production quantity equals produced quantity:
      - Submit the `job_card`.
    - Else:
      - Change `job_card` status to **"On Hold"**.
  - Else:
    - Close the open time log **without job completion**.
    - Change `job_card` status to **"On Hold"**.
- Change the barcode group status to **"In Progress"**.
- Start timer with the employee.
- Change `job_card` status to **"Work In Progress"**.

### "In Progress"
- **`quality_data` is required** in the request body.
- If the barcode has **not "Completed"** `job_card` in it's `operation_states` table (except the job_card with the operation **"Sevkiyat"**):
  - **Throw an error**: "This item has unfinished `job_cards`. All jobs must be finished before quality control."
- If at least one criterion is **not passed**:
  - `corrections.required_operations` is required in `quality_data`.
  - Get the last `job_card` for each `required_operation`.
  - Create a **corrective `job_card`** on top of that
  - Add that corrective `job_card` to `operation_states` list in `TesDetay`.
  - Set the current barcode status to **"Correction"**.
  - Close the open time log **without job completion**.
  - Set the current `job_card` status to **"On Hold"**.
- Else:
  - Set barcode group status to **"Completed"**.
  - If all barcodes with the same `sanal_adet` are completed:
    - Close the open time log with **1 job completed**.
    - If total production quantity equals produced quantity:
      - Submit the `job_card`.
    - Else:
      - Change `job_card` status to **"On Hold"**.
  - Else:
    - Close the open time log **without job completion**.
    - Change `job_card` status to **"On Hold"**.

### "Completed"
- **Throw an error**: "This operation for this item is already completed."

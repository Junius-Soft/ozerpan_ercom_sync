# 🧾 Market App ↔ ERPNext API Integration Guide

This document explains how your **React-based Market App** can communicate with your **ERPNext (Frappe)** backend using custom API endpoints.

---

## 🌐 Base URL

```
https://erp.yoursite.com
```

Replace with your actual ERPNext instance domain.

---

## 🔐 Login to Frappe

### Endpoint

```
POST /api/method/login
```

### Headers

```
Content-Type: application/x-www-form-urlencoded
```

### Body

```
usr=dealer@example.com
pwd=your_password
```

### Example in React

```js
const login = async (email, password) => {
  const res = await fetch("https://erp.yoursite.com/api/method/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    credentials: "include", // Include cookies for session auth
    body: new URLSearchParams({ usr: email, pwd: password }),
  });

  if (!res.ok) throw new Error("Login failed");
  return await res.json();
};
```

> ✅ **Note:** You must use `credentials: "include"` for all requests to keep the login session (via cookies).

---

## 📥 Get Last 10 Orders

### Endpoint

```
GET /api/method/ozerpan_ercom_sync.market.api.get_ercom_orders
```

### Optional Query Parameter

- `search_filter`: string – filter by order number or other criteria

### Example in React

```js
const getOrders = async (searchFilter) => {
  const url = new URL("https://erp.yoursite.com/api/method/ozerpan_ercom_sync.market.api.get_ercom_orders");

  if (searchFilter) {
    url.searchParams.append("search_filter", searchFilter);
  }

  const res = await fetch(url.toString(), {
    method: "GET",
    credentials: "include",
  });

  if (!res.ok) throw new Error("Failed to fetch orders");

  const data = await res.json();
  return data.message; // order data
};
```

---

## 📤 Create Sales Order

### Endpoint

```
POST /api/method/ozerpan_ercom_sync.market.api.sales_order
```

### Headers

```
Content-Type: application/json
```

### Example Request Body

```json
{
  "data": [
    {
      "name": "POZ 1",
      "quantity": 5,
      "production_materials": {
        "profiles": [
          {
            "stock_code": "353115703000",
            "type": "lamel",
            "description": "77 lik Celik Lamel Metalik Gri",
            "measure": 866.0,
            "right_angle": 0.0,
            "left_angle": 0.0,
            "quantity": 11
          }
        ],
        "accessories": [
          {
            "stock_code": "352441523000",
            "description": "250 Yan Kapak 45 Motor Metalik Gri",
            "quantity": 1
          }
        ]
      }
    },
    {
      "name": "POZ 2",
      "quantity": 1,
      "production_materials": {
        "profiles": [
          {
            "stock_code": "353115703000",
            "type": "lamel",
            "description": "77 lik Celik Lamel Metalik Gri",
            "measure": 866.0,
            "right_angle": 0.0,
            "left_angle": 0.0,
            "quantity": 11
          }
        ],
        "accessories": [
          {
            "stock_code": "352441523000",
            "description": "250 Yan Kapak 45 Motor Metalik Gri",
            "quantity": 1
          }
        ]
      }
    }
  ]
}
```

### Example in React

```js
const postSalesOrder = async (orderData) => {
  const res = await fetch("https://erp.yoursite.com/api/method/ozerpan_ercom_sync.market.api.sales_order", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include",
    body: JSON.stringify({ data: orderData }),
  });

  if (!res.ok) throw new Error("Failed to create sales order");

  const data = await res.json();
  return data.message; // response from backend
};
```

---

## ✅ API Summary

| Action               | Endpoint                                                              | Method | Auth Required |
|----------------------|-----------------------------------------------------------------------|--------|----------------|
| Login                | `/api/method/login`                                                  | POST   | ❌             |
| Get Orders           | `/api/method/ozerpan_ercom_sync.market.api.get_ercom_orders`         | GET    | ✅             |
| Create Sales Order   | `/api/method/ozerpan_ercom_sync.market.api.sales_order`              | POST   | ✅             |

---

## 🛠 Setup Checklist

### CORS Settings

Make sure your ERPNext allows cross-origin requests from your Market App:

```json
"allow_cors": "https://your-market-app.com"
```

Or use the **CORS Doctype** in ERPNext (v14+):
- Doctype: `CORS`
- Origin: `https://your-market-app.com`
- Allowed Methods: `GET, POST, OPTIONS`

---

## 🧠 Notes

- All Frappe endpoints must be decorated with `@frappe.whitelist()`
- To access the currently logged-in user in Python, use `frappe.session.user`
- Always use `credentials: "include"` when calling Frappe from a separate frontend (React, etc.)

---

# Ozerpan Ercom Sync Development Guide

## Setup & Commands

- **Run Frappe development server**: `bench start`
- **Run tests**: `bench run-tests --app ozerpan_ercom_sync`
- **Run specific test**: `bench run-tests --module ozerpan_ercom_sync.ozerpan_ercom_sync.doctype.tesdetay.test_tesdetay`
- **Lint code**: `flake8 ozerpan_ercom_sync`
- **Format code**: `black ozerpan_ercom_sync`
- **Type checking**: `mypy ozerpan_ercom_sync`

## Code Style Guidelines

- **Imports**: Sort imports with standard library first, then third-party, then local
- **Type hints**: Use Python type hints for function parameters and return values
- **Naming**: Use snake_case for functions/variables, PascalCase for classes
- **Error handling**: Use specific exceptions with meaningful error messages
- **Documentation**: Document classes and complex functions with docstrings
- **Class structure**: Follow Frappe document class patterns for DocTypes
- **Max line length**: 88 characters (Black default)
- **Async code**: Use appropriate error handling in try/except blocks
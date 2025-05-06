from .helpers import delete_related_capacity_docs


def before_cancel(doc, method):
    delete_related_capacity_docs(production_plan_docname=doc.name)

from .helpers import delete_related_capacity_docs


def on_trash(doc, method):
    delete_related_capacity_docs(production_plan_docname=doc.name)

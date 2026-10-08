import random

from .. import udB


def list_emp():
    return udB.get_key("EMP") or {}


def add_emp(emp, docid):
    ok = list_emp()
    ok.setdefault(emp, []).append(int(docid))
    return udB.set_key("EMP", ok)


def rem_emp(emp, docid):
    ok = list_emp()
    if ok.get(emp):
        if int(docid) in ok[emp]:
            ok[emp].remove(int(docid))
            if not ok[emp]:
                del ok[emp]
            return udB.set_key("EMP", ok)


def get_emp(emp):
    ok = list_emp()
    if ok.get(emp):
        return random.choice([int(i) for i in ok[emp]])


def is_emp(docid):
    ok = list_emp()
    for emp, docids in ok.items():
        if int(docid) in docids:
            return emp
    return None

from .. import udB


def get_stored():
    return udB.get_key("FILE_STORE") or {}


def store_msg(name, msg_id):
    all = get_stored()
    all.update({name: msg_id})
    return udB.set_key("FILE_STORE", all)


def list_all_stored_msgs():
    all = get_stored()
    return list(all.keys())


def get_stored_msg(name):
    all = get_stored()
    if all.get(name):
        return all[name]


def del_stored(name):
    all = get_stored()
    all.pop(name)
    return udB.set_key("FILE_STORE", all)

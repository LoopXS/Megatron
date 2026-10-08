import math
from telethon import events
from . import *

# ========== Database ==========

drugs = {
    "Meloxicam": {
        "category": "ضد التهاب",
        "forms": {
            "قرص 7.5": {
                "form": "tab",
                "carp": {"طوطی": 1.0, "کبوتر": 0.8, "قناری": 0.6},
                "com": 7.5
            },
            "قرص 15": {
                "form": "tab",
                "carp": {"طوطی": 1.0, "کبوتر": 0.8},
                "com": 15
            },
            "ویال درصدی": {
                "form": "vial%",
                "carp": {"طوطی": 0.5, "قناری": 0.3},
                "com": 2
            }
        }
    },
    "Amoxicillin": {
        "category": "آنتی‌بیوتیک",
        "forms": {
            "کپسول 250": {
                "form": "cap",
                "carp": {"طوطی": 10, "کبوتر": 8},
                "com": 250
            },
            "سوسپانسیون 125mg/5ml": {
                "form": "susp",
                "carp": {"طوطی": 10, "کبوتر": 8},
                "com": 25  # mg/ml (125 mg ÷ 5 ml)
            }
        }
    },
    "Dexamethasone": {
        "category": "کورتیکواستروئید",
        "forms": {
            "آمپول 4mg/ml": {
                "form": "amp",
                "carp": {"طوطی": 0.2, "قناری": 0.15},
                "com": 4
            }
        }
    }
}

# ========== Helper Functions ==========

def cc_to_drops(dose_cc):
    if 0.04 <= dose_cc <= 0.05:
        return 1
    raw = dose_cc / 0.04
    return math.floor(raw + 0.5)

async def calc_dose(name, form_info, species, weight_grams):
    form = form_info["form"]
    carp = form_info["carp"][species]
    com = form_info["com"]
    weight_kg = weight_grams / 1000

    if form in ["tab", "cap"]:
        dose_mg = weight_kg * carp * 10
        dose_cc = dose_mg / com
        water_cc = 10
        while dose_cc < 0.04:
            water_cc *= 2
            dose_cc = (weight_kg * carp * water_cc) / com
        drops = cc_to_drops(dose_cc)

        return (
            f"💊 دارو: {name}\n"
            f"📦 شکل: {'قرص' if form=='tab' else 'کپسول'}\n"
            f"🕊️ گونه: {species}\n"
            f"⚖️ وزن: {weight_grams} گرم\n"
            f"🔢 دوز: {dose_cc:.2f} cc\n"
            f"🥤 در {water_cc}cc آب حل شود\n"
            f"💧 معادل: {drops} قطره"
        )

    elif form in ["amp", "susp"]:
        dose_cc = (weight_kg * carp) / com
        insulin_units = dose_cc * 100
        return (
            f"💉 دارو: {name}\n"
            f"📦 شکل: {'آمپول' if form=='amp' else 'سوسپانسیون'} ({com} mg/ml)\n"
            f"🕊️ گونه: {species}\n"
            f"⚖️ وزن: {weight_grams} گرم\n"
            f"🔢 دوز: {dose_cc:.2f} cc\n"
            f"💧 معادل: {insulin_units:.0f} واحد انسولینی"
        )

    elif form == "vial%":
        dose_cc = (weight_kg * carp) / (com * 10)
        insulin_units = dose_cc * 100
        return (
            f"💉 دارو: {name}\n"
            f"📦 شکل: ویال {com}%\n"
            f"🕊️ گونه: {species}\n"
            f"⚖️ وزن: {weight_grams} گرم\n"
            f"🔢 دوز: {dose_cc:.2f} cc\n"
            f"💧 معادل: {insulin_units:.0f} واحد انسولینی"
        )

    else:
        return "❌ فرم دارو ناشناخته است."


# ========== Command Handler ==========

@asst_cmd(pattern="dose")
async def _(event):
    categories = {}
    for name, info in drugs.items():
        cat = info["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(name)

    async with asst.conversation(event.chat_id) as conv:
        cat_text = "📋 دسته‌های دارویی:\n"
        for i, cat in enumerate(categories.keys(), 1):
            cat_text += f"{i}. {cat}\n"
        cat_text += "\n✨ شماره دسته مد نظر را ارسال کنید (یا `کنسل` برای لغو)."
        await conv.send_message(cat_text)

        resp_cat = await conv.get_response(timeout=30)
        verify_cat = resp_cat.raw_text.strip()
        if verify_cat.startswith("کنسل"):
            await conv.send_message("فرایند کنسل شد ❌")
            return
        if not verify_cat.isnumeric() or int(verify_cat) not in range(1, len(categories)+1):
            await conv.send_message("❌ شماره دسته نامعتبر است.")
            return

        cat_id = int(verify_cat)
        selected_cat = list(categories.keys())[cat_id-1]
        drugs_list = categories[selected_cat]

        text = f"📦 داروهای دسته {selected_cat}:\n\n"
        for i, name in enumerate(drugs_list, 1):
            text += f"{i}. {name}\n"
        text += "\n0️⃣ داروی لیست نشده\n✨ شماره دارو را وارد کنید (یا `کنسل` برای لغو)."
        await conv.send_message(text)

        resp_drug = await conv.get_response(timeout=60)
        verify_drug = resp_drug.raw_text.strip()
        if verify_drug.startswith("کنسل"):
            await conv.send_message("فرایند کنسل شد ❌")
            return

        if verify_drug == "0":
            drug_name = "داروی لیست‌نشده"

            form_options = [
                "tab (قرص)",
                "cap (کپسول)",
                "vial% (ویال درصدی)",
                "amp (آمپول)",
                "susp (سوسپانسیون)"
            ]
            msg = "💊 فرم دارو را انتخاب کنید:\n"
            for i, f_name in enumerate(form_options, 1):
                msg += f"{i}. {f_name}\n"
            msg += "\n✨ شماره فرم را ارسال کنید (یا `کنسل` برای لغو)."
            await conv.send_message(msg)

            resp_form = await conv.get_response(timeout=60)
            verify_form = resp_form.raw_text.strip()
            if verify_form.startswith("کنسل"):
                await conv.send_message("فرایند کنسل شد ❌")
                return
            if not verify_form.isnumeric() or int(verify_form) not in range(1, len(form_options)+1):
                await conv.send_message("❌ شماره فرم نامعتبر است.")
                return

            form_value = form_options[int(verify_form)-1].split(" ")[0]

            await conv.send_message("🔢 دوز فارماکوپه را به‌صورت عدد وارد کنید:")
            resp_carp = await conv.get_response(timeout=60)
            try:
                carp_value = float(resp_carp.raw_text.strip())
            except ValueError:
                await conv.send_message("❌ عدد معتبر وارد کنید.")
                return

            await conv.send_message("⚗️ دوز تجاری دارو را وارد کنید:")
            resp_com = await conv.get_response(timeout=60)
            try:
                com_value = float(resp_com.raw_text.strip())
            except ValueError:
                await conv.send_message("❌ عدد معتبر وارد کنید.")
                return

            form_info = {
                "form": form_value,
                "carp": {"عمومی": carp_value},
                "com": com_value
            }

        else:
            if not verify_drug.isnumeric() or int(verify_drug) not in range(1, len(drugs_list)+1):
                await conv.send_message("❌ شماره دارو نامعتبر است.")
                return

            drug_name = drugs_list[int(verify_drug)-1]
            drug_info = drugs[drug_name]
            forms = drug_info["forms"]
            form_names = list(forms.keys())

            msg = "💊 فرم‌های موجود:\n"
            for i, f_name in enumerate(form_names, 1):
                msg += f"{i}. {f_name}\n"
            msg += "\n✨ شماره فرم مد نظر را وارد کنید (یا `کنسل` برای لغو)."
            await conv.send_message(msg)

            resp_form = await conv.get_response(timeout=30)
            verify_form = resp_form.raw_text.strip()
            if verify_form.startswith("کنسل"):
                await conv.send_message("فرایند کنسل شد ❌")
                return
            if not verify_form.isnumeric() or int(verify_form) not in range(1, len(form_names)+1):
                await conv.send_message("❌ شماره فرم نامعتبر است.")
                return

            form_name = form_names[int(verify_form)-1]
            form_info = forms[form_name]

        await conv.send_message("⚖️ وزن پرنده را به گرم وارد کنید (یا `کنسل` برای لغو).")
        resp_w = await conv.get_response(timeout=60)
        weight_raw = resp_w.raw_text.strip()
        if weight_raw.startswith("کنسل"):
            await conv.send_message("فرایند کنسل شد ❌")
            return
        try:
            weight_grams = float(weight_raw)
        except ValueError:
            await conv.send_message("❌ لطفا عدد معتبر وارد کنید.")
            return

        results = []
        for species in form_info["carp"]:
            res = await calc_dose(drug_name, form_info, species, weight_grams)
            results.append(res)

        final_msg = "\n\n".join(results)
        if drug_name == "داروی لیست‌نشده":
            final_msg = "⚠️ این دارو در دیتابیس ثبت نشده است.\n\n" + final_msg

        await conv.send_message(final_msg)

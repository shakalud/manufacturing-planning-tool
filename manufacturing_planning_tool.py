import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from collections import Counter, defaultdict
import sqlite3
import datetime
import os
import tempfile
import html


# ====== Глобальные переменные ======
panels = []           # список хазитов: [[(size_mm, count), ...], ...] или для крыши: [(size_mm, count, m_role, m_val)]
current_hazit = []    # текущий редактируемый хазит
DB_PATH = "hazit.db"

# === Время ПК строкой ===
def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# === Инициализация/миграция БД ===
def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            azmana_no TEXT NOT NULL,
            thickness_mm INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS metals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            role TEXT CHECK(role IN ('up','down')) NOT NULL,
            label TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS packs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            hazit_index INTEGER NOT NULL,
            pack_index INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pack_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pack_id INTEGER NOT NULL,
            size_mm INTEGER NOT NULL,
            count INTEGER NOT NULL,
            mufa_role TEXT CHECK(mufa_role IN ('F','R')) NULL,
            mufa_value INTEGER NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(pack_id) REFERENCES packs(id) ON DELETE CASCADE
        )
    """)

    # мягкая миграция для уже существующей БД
    def ensure_column(table, coldef):
        col = coldef.split()[0]
        cur.execute(f"PRAGMA table_info({table})")
        if not any(r[1] == col for r in cur.fetchall()):
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {coldef}")

    ensure_column("orders", "created_at TEXT NOT NULL DEFAULT '1970-01-01 00:00:00'")
    ensure_column("orders", "updated_at TEXT")
    ensure_column("metals", "created_at TEXT NOT NULL DEFAULT '1970-01-01 00:00:00'")
    ensure_column("packs",  "created_at TEXT NOT NULL DEFAULT '1970-01-01 00:00:00'")
    ensure_column("pack_items", "mufa_role TEXT")
    ensure_column("pack_items", "mufa_value INTEGER")
    ensure_column("pack_items", "created_at TEXT NOT NULL DEFAULT '1970-01-01 00:00:00'")

    con.commit()
    con.close()


# === OCR удалён: версия только с ручным вводом ===

# === Пересчёт всех хавелот ===
def compute_all_packs():
    """
    Возвращает:
      - если НЕ крыша: list[hazit -> list[pack -> list[(size_mm, count)]]]
      - если крыша: list[hazit -> list[((role,val), list[pack -> list[(size_mm, count, role, val)]]])]]
    """
    all_result = []
    template_on = template_mode_var.get()
    is_roof = roof_mode_var.get()

    # шаблон
    if template_on and is_roof:
        template = [8, 8, 8, 6]
    elif template_on and not is_roof:
        template = [9, 9, 8]
    else:
        template = None

    try:
        panels_per_pack = int(pack_size_spinbox.get())
        if panels_per_pack <= 0:
            raise ValueError
    except Exception:
        panels_per_pack = 10

    for hazit in panels:
        if not is_roof:
            flat = [size for size, count in hazit for _ in range(count)]
            flat.sort(reverse=True)
            packs = []

            if template:
                idx = 0
                rem = Counter(flat)
                while sum(rem.values()) > 0:
                    need = template[idx]
                    pack = []
                    for size in sorted(list(rem.keys()), reverse=True):
                        if need == 0:
                            break
                        take = min(rem[size], need)
                        if take > 0:
                            pack.append((size, take))
                            rem[size] -= take
                            need -= take
                            if rem[size] == 0:
                                del rem[size]
                    packs.append(pack)
                    idx = (idx + 1) % len(template)
            else:
                counts = Counter(flat)
                cur, in_pack = [], 0
                for size, cnt in counts.items():
                    while cnt > 0:
                        free = panels_per_pack - in_pack
                        if free > 0:
                            take = min(cnt, free)
                            cur.append((size, take))
                            in_pack += take
                            cnt -= take
                        if in_pack == panels_per_pack:
                            packs.append(cur)
                            cur, in_pack = [], 0
                if cur:
                    packs.append(cur)

            all_result.append(packs)

        else:
            groups = defaultdict(list)  # (role,val) -> [(size,cnt)]
            for item in hazit:
                if len(item) == 4:
                    size, cnt, role, val = item
                else:
                    size, cnt, role, val = item[0], item[1], None, None
                groups[(role, val)].append((size, cnt))

            keys = []
            for (role, val) in groups:
                if role == 'F':
                    keys.append((0, val if val is not None else 0, role, val))
                elif role == 'R':
                    keys.append((1, -(val if val is not None else 0), role, val))
                else:
                    keys.append((2, 0, role, val))
            keys.sort()

            ordered = []
            for _, _, role, val in keys:
                items = []
                for size, cnt in groups[(role, val)]:
                    items.extend([size] * cnt)
                items.sort(reverse=True)

                packs = []
                if template:
                    idx = 0
                    rem = Counter(items)
                    while sum(rem.values()) > 0:
                        need = template[idx]
                        pack = []
                        for size in sorted(list(rem.keys()), reverse=True):
                            if need == 0:
                                break
                            take = min(rem[size], need)
                            if take > 0:
                                pack.append((size, take, role, val))
                                rem[size] -= take
                                need -= take
                                if rem[size] == 0:
                                    del rem[size]
                        packs.append(pack)
                        idx = (idx + 1) % len(template)
                else:
                    counts = Counter(items)
                    cur, in_pack = [], 0
                    for size, cnt in counts.items():
                        while cnt > 0:
                            free = panels_per_pack - in_pack
                            if free > 0:
                                take = min(cnt, free)
                                cur.append((size, take, role, val))
                                in_pack += take
                                cnt -= take
                            if in_pack == panels_per_pack:
                                packs.append(cur)
                                cur, in_pack = [], 0
                    if cur:
                        packs.append(cur)

                ordered.append(((role, val), packs))
            all_result.append(ordered)

    return all_result

# === Общий метраж текущего хазита ===
def update_current_total():
    s = 0.0
    for item in current_hazit:
        s += (item[0] / 1000) * item[1]
    current_total_label.config(text=f"Current batch total: {s:.2f} m")

# === Обновляем текущий список хазита ===
def update_current_hazit_list():
    current_hazit_list.delete(0, tk.END)
    is_roof = roof_mode_var.get()
    for item in current_hazit:
        if is_roof and len(item) == 4:
            size, count, role, val = item
            current_hazit_list.insert(tk.END, f"Size: {size} mm, Qty: {count}, Joint: {role}{'' if val is None else f'={val}'}")
        else:
            size, count = item[0], item[1]
            current_hazit_list.insert(tk.END, f"Size: {size} mm, Qty: {count}")
    update_current_total()

def submit_entry(event=None):
    global current_hazit
    try:
        size = int(size_entry.get())
        count = int(count_entry.get())
        if roof_mode_var.get():
            role = mufa_role_var.get()
            try:
                val = int(mufa_value_spin.get())
            except:
                val = None
            if val is not None:
                val = max(50, min(300, val))
            current_hazit.append((size, count, role, val))
        else:
            current_hazit.append((size, count))

        update_current_hazit_list()
        size_entry.delete(0, tk.END)
        count_entry.delete(0, tk.END)
        size_entry.focus()
    except ValueError:
        messagebox.showerror("Ошибка ввода", "Введите корректные числа.")

def finish_hazit():
    global current_hazit
    if current_hazit:
        panels.append(current_hazit)
        current_hazit = []
        update_panel_list()
        current_hazit_list.delete(0, tk.END)
        update_current_total()

def build_receipt_text():
    """Узкая печатная версия под катушку 56 мм (рабочая ширина около 52 мм)."""
    all_struct = compute_all_packs()
    is_roof = roof_mode_var.get()
    azmana = azmana_entry.get().strip()
    top_metal = metal_up_entry.get().strip()
    bottom_metal = metal_down_entry.get().strip()

    lines = []
    if azmana:
        lines.append(f"AZ: {azmana}")
        if top_metal:
            lines.append(f"UP: {top_metal}")
        if bottom_metal:
            lines.append(f"DN: {bottom_metal}")
        lines.append("-" * 22)

    def hazit_total_m(hazit_list):
        return sum((it[0] / 1000.0) * it[1] for it in hazit_list)

    grand_total_m = 0.0

    for hazit_index, data in enumerate(all_struct, start=1):
        src_hazit = panels[hazit_index - 1] if hazit_index - 1 < len(panels) else []
        total_m_this = hazit_total_m(src_hazit)
        grand_total_m += total_m_this

        if not is_roof:
            packs = data
            lines.append(f"H{hazit_index}:")
            for idx, pack in enumerate(packs, start=1):
                if len(pack) == 1:
                    size, cnt = pack[0]
                    lines.append(f"{idx:02d} {size} x{cnt}")
                else:
                    first = True
                    for size, cnt in pack:
                        if first:
                            lines.append(f"{idx:02d} {size} x{cnt}")
                            first = False
                        else:
                            lines.append(f"   {size} x{cnt}")
            lines.append(f"M{hazit_index}: {total_m_this:.2f}m")
            lines.append("")
        else:
            lines.append(f"R{hazit_index}:")
            for (role, val), packs in data:
                lines.append(f"{role}{'' if val is None else val}:")
                for idx, pack in enumerate(packs, start=1):
                    first = True
                    for size, cnt, _, _ in pack:
                        if first:
                            lines.append(f"{idx:02d} {size} x{cnt}")
                            first = False
                        else:
                            lines.append(f"   {size} x{cnt}")
            lines.append(f"M{hazit_index}: {total_m_this:.2f}m")
            lines.append("")

    if azmana:
        lines.append(f"AZ: {azmana}")
    lines.append(f"TOTAL: {grand_total_m:.2f}m")

    return "\n".join(lines).strip() + "\n"


def calculate_packs():
    result_text.delete('1.0', tk.END)
    text = build_receipt_text()
    if not text.strip() or text.strip() == "TOTAL: 0.00m":
        messagebox.showwarning("Расчёт", "Нет завершённых хазитов для расчёта.")
        return
    result_text.insert(tk.END, text)

def update_panel_list():
    panel_list.delete(0, tk.END)
    is_roof = roof_mode_var.get()
    for hazit_index, hazit in enumerate(panels, start=1):
        for item in hazit:
            if is_roof and len(item) == 4:
                size, count, role, val = item
                panel_list.insert(tk.END, f"Size: {size} mm, Qty: {count}, Joint: {role}{'' if val is None else f'={val}'} (Batch {hazit_index})")
            else:
                size, count = item[0], item[1]
                panel_list.insert(tk.END, f"Size: {size} mm, Qty: {count} (Batch {hazit_index})")

# === Удаление выбранного элемента по ПКМ ===
def delete_selected_from_current_hazit():
    selection = current_hazit_list.curselection()
    if not selection:
        return
    index = selection[0]
    del current_hazit[index]
    update_current_hazit_list()

# === Полная очистка всей программы ===
def clear_all_data():
    global current_hazit, panels
    if messagebox.askyesno("Подтверждение", "Очистить ВСЕ данные?"):
        current_hazit.clear()
        panels.clear()
        current_hazit_list.delete(0, tk.END)
        panel_list.delete(0, tk.END)
        result_text.delete("1.0", tk.END)
        update_current_total()

# === Печать узкого чека 52 мм ===
def print_receipt():
    text = result_text.get("1.0", tk.END).strip()
    if not text:
        calculate_packs()
        text = result_text.get("1.0", tk.END).strip()

    if not text:
        messagebox.showwarning("Печать", "Нет данных для печати.")
        return

    # Делаем HTML с жёсткой шириной 52 мм. Обычно браузер/просмотрщик печатает это аккуратнее, чем TXT.
    safe_text = html.escape(text)
    html_doc = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
@page {{ size: 52mm auto; margin: 0; }}
html, body {{ margin: 0; padding: 0; width: 52mm; }}
pre {{
  margin: 0;
  padding: 1mm 1mm;
  width: 50mm;
  box-sizing: border-box;
  font-family: Consolas, 'Courier New', monospace;
  font-size: 20pt;
  line-height: 1.15;
  white-space: pre-wrap;
}}
</style>
</head>
<body><pre>{safe_text}</pre></body>
</html>"""

    tmp_dir = tempfile.gettempdir()
    html_path = os.path.join(tmp_dir, "havela_52mm_print.html")
    txt_path = os.path.join(tmp_dir, "havela_52mm_print.txt")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_doc)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)

    try:
        if os.name == "nt":
            os.startfile(html_path, "print")
            messagebox.showinfo("Печать", "Отправила узкий чек на печать. Если принтер откроет предпросмотр — выбери ширину бумаги 56 мм / без полей.")
        else:
            messagebox.showinfo("Печать", f"Файл для печати создан:\n{html_path}")
    except Exception as e:
        try:
            os.startfile(html_path)
        except Exception:
            pass
        messagebox.showwarning("Печать", f"Автопечать не сработала:\n{e}\n\nОткрыла/создала файл:\n{html_path}")

# Оставил копирование как резерв через Ctrl+C из поля результата.

# === Вспомогательные для orders ===
def get_last_order_id(cur, azmana):
    cur.execute("SELECT id FROM orders WHERE azmana_no=? ORDER BY id DESC LIMIT 1", (azmana,))
    row = cur.fetchone()
    return row[0] if row else None

def create_order(cur, azmana, thickness):
    cur.execute(
        "INSERT INTO orders(azmana_no, thickness_mm, created_at, updated_at) VALUES(?,?,?,?)",
        (azmana, int(thickness or 0), now_str(), None)
    )
    return cur.lastrowid

# === Сохранить в БД (добавляет хавелы, +металлы если введены; толщину ставит только при создании или если была 0) ===
def save_to_db():
    azmana = azmana_entry.get().strip()
    if not azmana:
        messagebox.showerror("Сохранить в БД", "Укажи номер азманы.")
        return

    # толщина — только при первом заполнении
    try:
        thickness = int(thickness_entry.get() or 0)
    except ValueError:
        thickness = 0

    all_struct = compute_all_packs()
    if not panels and not all_struct:
        if not messagebox.askyesno("Внимание", "Хазиты/хавелоты пусты. Сохранить только азману/металлы?"):
            return

    metal_up = (metal_up_entry.get() or "").strip()
    metal_down = (metal_down_entry.get() or "").strip()

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    order_id = get_last_order_id(cur, azmana)
    if order_id is None:
        order_id = create_order(cur, azmana, thickness)
    else:
        # если в БД толщина 0 и введена ненулевая — проставим один раз
        cur.execute("SELECT thickness_mm FROM orders WHERE id=?", (order_id,))
        old_th = cur.fetchone()[0]
        if old_th == 0 and thickness > 0:
            cur.execute("UPDATE orders SET thickness_mm=? WHERE id=?", (thickness, order_id))

    # Металлы: если поля заполнены — добавим записи
    if metal_up:
        cur.execute("INSERT INTO metals(order_id, role, label, created_at) VALUES(?,?,?,?)",
                    (order_id, "up", metal_up, now_str()))
    if metal_down:
        cur.execute("INSERT INTO metals(order_id, role, label, created_at) VALUES(?,?,?,?)",
                    (order_id, "down", metal_down, now_str()))

    # Хавелоты
    is_roof = roof_mode_var.get()
    for h_idx, data in enumerate(all_struct, start=1):
        if not is_roof:
            packs = data
            for p_idx, pack in enumerate(packs, start=1):
                cur.execute("INSERT INTO packs(order_id, hazit_index, pack_index, created_at) VALUES(?,?,?,?)",
                            (order_id, h_idx, p_idx, now_str()))
                pack_id = cur.lastrowid
                for size_mm, cnt in pack:
                    cur.execute("""INSERT INTO pack_items
                                   (pack_id, size_mm, count, mufa_role, mufa_value, created_at)
                                   VALUES(?,?,?,?,?,?)""",
                                (pack_id, size_mm, cnt, None, None, now_str()))
        else:
            seq = 1
            for (role, val), packs in data:
                for pack in packs:
                    cur.execute("INSERT INTO packs(order_id, hazit_index, pack_index, created_at) VALUES(?,?,?,?)",
                                (order_id, h_idx, seq, now_str()))
                    pack_id = cur.lastrowid
                    for size_mm, cnt, r, v in pack:
                        cur.execute("""INSERT INTO pack_items
                                       (pack_id, size_mm, count, mufa_role, mufa_value, created_at)
                                       VALUES(?,?,?,?,?,?)""",
                                    (pack_id, size_mm, cnt, r, v, now_str()))
                    seq += 1

    con.commit()
    con.close()

    # очищаем поля металлов (удобно добивать следующими)
    if metal_up:  metal_up_entry.delete(0, tk.END)
    if metal_down: metal_down_entry.delete(0, tk.END)

    messagebox.showinfo("БД", f"Сохранено. Азмана {azmana} (order_id={order_id}).")

# === Обновить (металлы) — добавить ещё строки без замены ===
def update_metals():
    azmana = azmana_entry.get().strip()
    if not azmana:
        messagebox.showerror("Металлы", "Укажи номер азманы.")
        return

    metal_up = (metal_up_entry.get() or "").strip()
    metal_down = (metal_down_entry.get() or "").strip()
    if not metal_up and not metal_down:
        messagebox.showerror("Металлы", "Заполни поле «Металл (верх)» или «Металл (низ)».")
        return

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    order_id = get_last_order_id(cur, azmana)
    if order_id is None:
        # если нет — создадим заказ без толщины
        order_id = create_order(cur, azmana, 0)

    if metal_up:
        cur.execute("INSERT INTO metals(order_id, role, label, created_at) VALUES(?,?,?,?)",
                    (order_id, "up", metal_up, now_str()))
    if metal_down:
        cur.execute("INSERT INTO metals(order_id, role, label, created_at) VALUES(?,?,?,?)",
                    (order_id, "down", metal_down, now_str()))

    con.commit()
    con.close()

    metal_up_entry.delete(0, tk.END)
    metal_down_entry.delete(0, tk.END)
    messagebox.showinfo("Металлы", f"Добавлено. Азмана {azmana} (order_id={order_id}).")

# === Обновить азману — заменить металлы и хавелоты; толщину обновить здесь ===
def update_order():
    azmana = azmana_entry.get().strip()
    if not azmana:
        messagebox.showerror("Обновить азману", "Укажи номер азманы.")
        return

    try:
        new_thickness = int(thickness_entry.get() or 0)
    except ValueError:
        new_thickness = 0

    metal_up = (metal_up_entry.get() or "").strip()
    metal_down = (metal_down_entry.get() or "").strip()

    all_struct = compute_all_packs()

    if not messagebox.askyesno(
        "Подтверждение",
        "Будут ЗАМЕНЕНЫ хавелоты и металлы для последней записи этой азманы.\n"
        "Пустые поля металлов = удалить металлы. Продолжить?"
    ):
        return

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    order_id = get_last_order_id(cur, azmana)
    if order_id is None:
        messagebox.showerror("Обновить азману", "Такой азманы в БД ещё нет. Сначала нажми «Сохранить в БД».")
        con.close()
        return

    # Обновим толщину и updated_at (только тут)
    cur.execute("UPDATE orders SET thickness_mm=?, updated_at=? WHERE id=?",
                (new_thickness, now_str(), order_id))


    # Удалим старые металлы и хавелоты
    cur.execute("SELECT id FROM packs WHERE order_id=?", (order_id,))
    pack_ids = [r[0] for r in cur.fetchall()]
    if pack_ids:
        cur.executemany("DELETE FROM pack_items WHERE pack_id=?", [(pid,) for pid in pack_ids])
    cur.execute("DELETE FROM packs WHERE order_id=?", (order_id,))
    cur.execute("DELETE FROM metals WHERE order_id=?", (order_id,))

    # Вставим новые металлы (если заданы)
    if metal_up:
        cur.execute("INSERT INTO metals(order_id, role, label, created_at) VALUES(?,?,?,?)",
                    (order_id, "up", metal_up, now_str()))
    if metal_down:
        cur.execute("INSERT INTO metals(order_id, role, label, created_at) VALUES(?,?,?,?)",
                    (order_id, "down", metal_down, now_str()))

    # Вставим новые хавелоты
    is_roof = roof_mode_var.get()
    for h_idx, data in enumerate(all_struct, start=1):
        if not is_roof:
            packs = data
            for p_idx, pack in enumerate(packs, start=1):
                cur.execute("INSERT INTO packs(order_id, hazit_index, pack_index, created_at) VALUES(?,?,?,?)",
                            (order_id, h_idx, p_idx, now_str()))
                pack_id = cur.lastrowid
                for size_mm, cnt in pack:
                    cur.execute("""INSERT INTO pack_items
                                   (pack_id, size_mm, count, mufa_role, mufa_value, created_at)
                                   VALUES(?,?,?,?,?,?)""",
                                (pack_id, size_mm, cnt, None, None, now_str()))
        else:
            seq = 1
            for (role, val), packs in data:
                for pack in packs:
                    cur.execute("INSERT INTO packs(order_id, hazit_index, pack_index, created_at) VALUES(?,?,?,?)",
                                (order_id, h_idx, seq, now_str()))
                    pack_id = cur.lastrowid
                    for size_mm, cnt, r, v in pack:
                        cur.execute("""INSERT INTO pack_items
                                       (pack_id, size_mm, count, mufa_role, mufa_value, created_at)
                                       VALUES(?,?,?,?,?,?)""",
                                    (pack_id, size_mm, cnt, r, v, now_str()))
                    seq += 1

    con.commit()
    con.close()

    messagebox.showinfo("БД", f"Азмана {azmana} обновлена (order_id={order_id}).")

# === Открыть по азмане ===
def open_by_azmana():
    azmana = azmana_entry.get().strip()
    if not azmana:
        messagebox.showerror("Открыть", "Укажи номер азманы.")
        return

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT id, thickness_mm, created_at, updated_at FROM orders WHERE azmana_no=? ORDER BY id", (azmana,))
    orders = cur.fetchall()

    if not orders:
        con.close()
        messagebox.showinfo("Открыть", f"В БД нет записей по азмане {azmana}.")
        return

    lines = []
    lines.append(f"Order: {azmana}")

    for (order_id, thickness_mm, created_at, updated_at) in orders:
        header = f"\n=== Order ID: {order_id}"
        if thickness_mm is not None:
            header += f" | Thickness: {thickness_mm} мм"
        header += f" | Created: {created_at}"
        if updated_at and str(updated_at).strip():
            header += f" | Updated: {updated_at}"
        header += " ==="
        lines.append(header)

        # Металлы (без дат)
        cur.execute("SELECT role, COALESCE(label,'—') FROM metals WHERE order_id=? ORDER BY role, id", (order_id,))
        metals_rows = cur.fetchall()
        if metals_rows:
            ups = [lbl for role, lbl in metals_rows if role == "up"]
            downs = [lbl for role, lbl in metals_rows if role == "down"]
            lines.append("Top:")
            lines += [f"  {i}) {lbl}" for i, lbl in enumerate(ups, 1)] or ["  —"]
            lines.append("Bottom:")
            lines += [f"  {i}) {lbl}" for i, lbl in enumerate(downs, 1)] or ["  —"]
        else:
            lines.append("Metals: —")

        # Хавелоты (без дат)
        cur.execute("SELECT id, hazit_index, pack_index FROM packs WHERE order_id=? ORDER BY hazit_index, pack_index", (order_id,))
        pack_rows = cur.fetchall()
        if not pack_rows:
            lines.append("Packs: —")
        else:
            cur2 = con.cursor()
            current_h = None
            for pack_id, hazit_index, pack_index in pack_rows:
                if current_h != hazit_index:
                    lines.append(f"\nBatch {hazit_index}:")
                    current_h = hazit_index
                cur2.execute("""SELECT size_mm, count, mufa_role, mufa_value
                                FROM pack_items
                                WHERE pack_id=?
                                ORDER BY (mufa_role IS NOT 'F'), mufa_value, size_mm DESC""", (pack_id,))
                items = cur2.fetchall()
                def item_str(it):
                    sz, cnt, r, v = it
                    if r in ('F','R'):
                        return f"{sz} мм - {cnt} шт. (муффа {r}={v})"
                    return f"{sz} мм - {cnt} шт."
                details = ", ".join([item_str(x) for x in items]) if items else "—"
                lines.append(f"  Pack {pack_index}: {details}")

        # Итог по этому заказу
        cur.execute("""SELECT SUM(pi.size_mm * pi.count)
                       FROM pack_items pi
                       JOIN packs p ON pi.pack_id = p.id
                       WHERE p.order_id=?""", (order_id,))
        sum_mm = cur.fetchone()[0]
        order_total_m = (sum_mm or 0) / 1000.0
        lines.append(f"\nTotal for order (Order {order_id}): {order_total_m:.2f} м")

    # Общий итог по всей азмане
    cur.execute("""SELECT SUM(pi.size_mm * pi.count)
                   FROM pack_items pi
                   JOIN packs p ON pi.pack_id = p.id
                   JOIN orders o ON p.order_id = o.id
                   WHERE o.azmana_no=?""", (azmana,))
    grand_mm = cur.fetchone()[0]
    grand_total_m = (grand_mm or 0) / 1000.0
    lines.append(f"\n=== TOTAL for order {azmana}: {grand_total_m:.2f} м ===")

    con.close()
    text = "\n".join(lines)

    win = tk.Toplevel(root)
    win.title(f"Азмана {azmana}")
    win.geometry("900x650")

    txt = tk.Text(win, wrap="word")
    txt.pack(fill="both", expand=True)
    txt.insert("1.0", text)

    btn_frame = ttk.Frame(win)
    btn_frame.pack(fill="x")

    def copy_all():
        # СКОПИРОВАТЬ КРАТКО (для чековой бумаги)
        from collections import defaultdict

        con2 = sqlite3.connect(DB_PATH)
        cur2 = con2.cursor()

        # 1) Все order_id этой азманы
        cur2.execute("SELECT id FROM orders WHERE azmana_no=? ORDER BY id", (azmana,))
        order_ids = [r[0] for r in cur2.fetchall()]
        if not order_ids:
            con2.close()
            messagebox.showinfo("Копирование", "Нет данных по этой азмане.")
            return

        # 2) Металлы (уникальные, в порядке появления)
        ups, downs = [], []
        for oid in order_ids:
            cur2.execute("SELECT role, COALESCE(label,'') FROM metals WHERE order_id=? ORDER BY role, id", (oid,))
            for role, label in cur2.fetchall():
                label = label.strip()
                if not label:
                    continue
                if role == "up":
                    ups.append(label)
                elif role == "down":
                    downs.append(label)

        def uniq(seq):
            seen = set()
            out = []
            for x in seq:
                if x not in seen:
                    seen.add(x)
                    out.append(x)
            return out

        ups = uniq(ups)
        downs = uniq(downs)

        # 3) Хавелоты: обычные и «крыша» (муффы)
        normal_packs = []               # ["600x9,550x1", ...]
        roof_groups = defaultdict(list) # (role,val) -> ["700x8,600x2", ...]

        for oid in order_ids:
            cur2.execute("SELECT id FROM packs WHERE order_id=? ORDER BY hazit_index, pack_index", (oid,))
            for (pack_id,) in cur2.fetchall():
                cur2.execute("""SELECT size_mm, count, mufa_role, mufa_value
                                FROM pack_items
                                WHERE pack_id=?
                                ORDER BY size_mm DESC""", (pack_id,))
                items = cur2.fetchall()
                if not items:
                    continue

                # строка вида "600x9,550x1"
                pack_str = ",".join(f"{sz}x{cnt}" for sz, cnt, _, _ in items)

                # проверим единственную муффу у всех позиций
                roles = {(r, v) for _, _, r, v in items if r in ('F', 'R') and v is not None}
                if len(roles) == 1:
                    r, v = next(iter(roles))
                    roof_groups[(r, int(v))].append(pack_str)
                else:
                    normal_packs.append(pack_str)

        # 4) Сортировка групп: F по возрастанию, R по убыванию
        order_keys = []
        for (r, v) in roof_groups.keys():
            if r == 'F':
                order_keys.append((0, v, r, v))
            else:  # 'R'
                order_keys.append((1, -v, r, v))
        order_keys.sort()

        # 5) Сборка минимального текста
        out_lines = [f"Азмана {azmana}"]
        metals_bits = []
        if ups:
            metals_bits.append("В:" + ",".join(ups))
        if downs:
            metals_bits.append("Н:" + ",".join(downs))
        if metals_bits:
            out_lines.append(" ".join(metals_bits))

        n = 1
        for p in normal_packs:
            out_lines.append(f"{n}) {p}")
            n += 1

        for _, _, r, v in order_keys:
            out_lines.append(f"{r}{v}:")
            for p in roof_groups[(r, v)]:
                out_lines.append(f"{n}) {p}")
                n += 1

        con2.close()

        minimal = "\n".join(out_lines)
        root.clipboard_clear()
        root.clipboard_append(minimal)
        root.update()
        messagebox.showinfo("Копирование", "Краткий текст скопирован в буфер.")

    def save_txt():
        path = filedialog.asksaveasfilename(
            title="Сохранить в TXT",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt")]
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(txt.get("1.0", tk.END))
        messagebox.showinfo("Сохранено", f"Файл сохранён:\n{path}")

    ttk.Button(btn_frame, text="Скопировать", command=copy_all).pack(side="left", padx=5, pady=5)
    ttk.Button(btn_frame, text="Сохранить в TXT", command=save_txt).pack(side="left", padx=5, pady=5)


# ========================= GUI =========================
root = tk.Tk()

# Discord-style dark theme
BG = "#111827"
PANEL = "#1f2937"
INPUT = "#0b1020"
TEXT = "#f9fafb"
MUTED = "#9ca3af"
ACCENT = "#5865F2"
DANGER = "#991b1b"
BORDER = "#374151"

style = ttk.Style(root)
try:
    style.theme_use("clam")
except Exception:
    pass

root.configure(bg=BG)
style.configure("TFrame", background=BG)
style.configure("TLabel", background=BG, foreground=TEXT)
style.configure("TLabelframe", background=BG, foreground=TEXT, bordercolor=BORDER)
style.configure("TLabelframe.Label", background=BG, foreground=TEXT)
style.configure("TCheckbutton", background=BG, foreground=TEXT)
style.configure("TRadiobutton", background=BG, foreground=TEXT)
style.configure("TEntry", fieldbackground=INPUT, foreground=TEXT, insertcolor=TEXT)
style.configure("TSpinbox", fieldbackground=INPUT, foreground=TEXT, arrowsize=14)
style.configure("TButton", background=PANEL, foreground=TEXT, bordercolor=BORDER, focusthickness=1, focuscolor=ACCENT, padding=5)
style.map("TButton", background=[("active", "#374151")])
style.configure("Accent.TButton", background=ACCENT, foreground=TEXT)
style.map("Accent.TButton", background=[("active", "#4752c4")])
style.configure("Danger.TButton", background=DANGER, foreground=TEXT)
style.map("Danger.TButton", background=[("active", "#7f1d1d")])

root.title("Manufacturing Packing & Production Planning Tool")

root.grid_rowconfigure(0, weight=1)
root.grid_columnconfigure(0, weight=1)

frame = ttk.Frame(root, padding=10)
frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
frame.grid_rowconfigure(24, weight=1)
frame.grid_columnconfigure(1, weight=1)

# Параметры заказа / азманы
azmana_label = ttk.Label(frame, text="Order number:")
azmana_label.grid(row=0, column=0, sticky=tk.W)
azmana_entry = ttk.Entry(frame, width=20)
azmana_entry.grid(row=0, column=1, sticky=(tk.W, tk.E))

thickness_label = ttk.Label(frame, text="Panel thickness (mm):")
thickness_label.grid(row=1, column=0, sticky=tk.W)
thickness_entry = ttk.Entry(frame, width=15)
thickness_entry.grid(row=1, column=1, sticky=(tk.W, tk.E))

metal_up_label = ttk.Label(frame, text="Top metal:")
metal_up_label.grid(row=2, column=0, sticky=tk.W)
metal_up_entry = ttk.Entry(frame, width=20)
metal_up_entry.grid(row=2, column=1, sticky=(tk.W, tk.E))

metal_down_label = ttk.Label(frame, text="Bottom metal:")
metal_down_label.grid(row=3, column=0, sticky=tk.W)
metal_down_entry = ttk.Entry(frame, width=20)
metal_down_entry.grid(row=3, column=1, sticky=(tk.W, tk.E))

# --- Крыша / Муффа ---
roof_mode_var = tk.BooleanVar(value=False)
def toggle_roof():
    enabled = roof_mode_var.get()
    for child in mufa_frame.winfo_children():
        try:
            if hasattr(child, "state"):
                if enabled:
                    child.state(["!disabled"])
                else:
                    child.state(["disabled"])
            else:
                child.configure(state="normal" if enabled else "disabled")
        except Exception:
            pass

roof_check = ttk.Checkbutton(frame, text="Roof panel mode", variable=roof_mode_var, command=toggle_roof)
roof_check.grid(row=4, column=0, sticky=tk.W)

mufa_frame = ttk.LabelFrame(frame, text="Joint settings", padding=6)
mufa_frame.grid(row=4, column=1, sticky=(tk.W, tk.E))
mufa_frame.grid_columnconfigure(3, weight=1)

ttk.Label(mufa_frame, text="Type:").grid(row=0, column=0, sticky=tk.W)
mufa_role_var = tk.StringVar(value="F")
ttk.Radiobutton(mufa_frame, text="F", variable=mufa_role_var, value="F").grid(row=0, column=1, sticky=tk.W)
ttk.Radiobutton(mufa_frame, text="R", variable=mufa_role_var, value="R").grid(row=0, column=2, sticky=tk.W)

ttk.Label(mufa_frame, text="Value (50–300):").grid(row=0, column=3, sticky=tk.W, padx=(10,4))
mufa_value_spin = ttk.Spinbox(mufa_frame, from_=50, to=300, width=6)
mufa_value_spin.set(50)
mufa_value_spin.grid(row=0, column=4, sticky=tk.W)

toggle_roof()  # по умолчанию отключено

# Ввод строк текущего хазита
size_label = ttk.Label(frame, text="Panel size (mm):")
size_label.grid(row=5, column=0, sticky=tk.W)
size_entry = ttk.Entry(frame, width=15)
size_entry.grid(row=5, column=1, sticky=(tk.W, tk.E))
size_entry.bind("<Return>", submit_entry)

count_label = ttk.Label(frame, text="Quantity:")
count_label.grid(row=6, column=0, sticky=tk.W)
count_entry = ttk.Entry(frame, width=15)
count_entry.grid(row=6, column=1, sticky=(tk.W, tk.E))
count_entry.bind("<Return>", submit_entry)

add_button = ttk.Button(frame, text="Add row", command=submit_entry)
add_button.grid(row=7, column=0, columnspan=2, sticky=(tk.W, tk.E))

finish_hazit_button = ttk.Button(frame, text="Finish batch / roof", command=finish_hazit)
finish_hazit_button.grid(row=8, column=0, columnspan=2, sticky=(tk.W, tk.E))

template_mode_var = tk.BooleanVar()
template_mode_checkbox = ttk.Checkbutton(
    frame,
    text="Template packing mode (wall: 9-9-8 / roof: 8-8-8-6)",
    variable=template_mode_var
)
template_mode_checkbox.grid(row=10, column=0, columnspan=2, sticky=(tk.W, tk.E))

pack_size_label = ttk.Label(frame, text="Panels per pack:")
pack_size_label.grid(row=11, column=0, sticky=tk.W)
pack_size_spinbox = ttk.Spinbox(frame, from_=1, to=100, width=5)
pack_size_spinbox.set(10)
pack_size_spinbox.grid(row=11, column=1, sticky=(tk.W, tk.E))

calculate_button = ttk.Button(frame, text="Calculate packs", command=calculate_packs)
calculate_button.grid(row=12, column=0, columnspan=2, sticky=(tk.W, tk.E))

# Кнопки работы с БД
db_buttons = ttk.Frame(frame)
db_buttons.grid(row=13, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(6,2))
ttk.Button(db_buttons, text="Save to database", command=save_to_db).pack(side="left", expand=True, fill="x", padx=2)
ttk.Button(db_buttons, text="Add metals", command=update_metals).pack(side="left", expand=True, fill="x", padx=2)
ttk.Button(db_buttons, text="Open order", command=open_by_azmana).pack(side="left", expand=True, fill="x", padx=2)
ttk.Button(db_buttons, text="Replace order", command=update_order).pack(side="left", expand=True, fill="x", padx=2)

# Списки/итоги
current_hazit_label = ttk.Label(frame, text="Current batch / roof:")
current_hazit_label.grid(row=14, column=0, sticky=tk.W)
current_hazit_list = tk.Listbox(frame, height=6)
current_hazit_list.grid(row=14, column=1, sticky=(tk.W, tk.E))

current_total_label = ttk.Label(frame, text="Current batch total: 0.00 m")
current_total_label.grid(row=15, column=0, sticky=tk.W)

panel_list = tk.Listbox(frame, height=6)
panel_list.grid(row=16, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))

result_text = tk.Text(frame, height=12, width=60)
result_text.grid(row=17, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))

# Управление
print_button = ttk.Button(frame, text="Print 52 mm", command=print_receipt)
print_button.grid(row=18, column=0, columnspan=2, sticky=(tk.W, tk.E))

clear_all_button = ttk.Button(frame, text="Clear all", command=clear_all_data)
clear_all_button.grid(row=19, column=0, columnspan=2, sticky=(tk.W, tk.E))


# Apply dark colors to classic Tk widgets
for widget in (current_hazit_list, panel_list):
    widget.configure(bg=INPUT, fg=TEXT, selectbackground=ACCENT, selectforeground=TEXT,
                     highlightbackground=BORDER, highlightcolor=ACCENT, relief="solid", borderwidth=1)
result_text.configure(bg=INPUT, fg=TEXT, insertbackground=TEXT,
                      highlightbackground=BORDER, highlightcolor=ACCENT, relief="solid", borderwidth=1)

try:
    calculate_button.configure(style="Accent.TButton")
    clear_all_button.configure(style="Danger.TButton")
except Exception:
    pass

# Контекстное меню
current_menu = tk.Menu(root, tearoff=0)
current_menu.add_command(label="Delete selected", command=delete_selected_from_current_hazit)
current_hazit_list.bind("<Button-3>", lambda event: current_menu.tk_popup(event.x_root, event.y_root))

# Старт
init_db()
size_entry.focus()
root.mainloop()

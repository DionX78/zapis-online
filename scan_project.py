import os
from datetime import datetime

# ============================================================
# УНИВЕРСАЛЬНЫЕ НАСТРОЙКИ (одинаковы для любого проекта)
# ============================================================

EXCLUDE_DIRS = {
    ".venv", "venv", ".git", "__pycache__", ".vscode",
    "uploads", "alembic", "backups", "logs",
    "node_modules", "dist", "build", ".idea",
}

EXCLUDE_FILES = {
    "package-lock.json",
    "yarn.lock",
    "booking.db",
    "scan_project.py",
}

INCLUDE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".json", ".yml", ".yaml", ".sh",
    ".html", ".css", ".md", ".txt",
    ".service", ".snippet", ".example",
}

OUTPUT_PREFIX = "project_dump"
MAX_FILE_SIZE = 10 * 1024 * 1024      # 10 МБ — с явной пометкой в статистике
HARD_LIMIT_SIZE = 50 * 1024 * 1024    # 50 МБ — жёсткий предохранитель


# ============================================================
# ПРОЕКТНЫЕ ИСКЛЮЧЕНИЯ — только для MAX Booking Bot
# Универсальная часть выше от этого блока не зависит.
# ============================================================

# Папки по ОТНОСИТЕЛЬНОМУ ПУТИ от корня проекта.
# НЕ трогают одноимённые папки в других местах:
# например, "mini/" с исходниками — не затронут, а "static/mini/" — исключён.
PROJECT_EXCLUDE_PATHS = {
    "static/mini",   # скомпилированные Vite-бандлы (JS + CSS + собранный index.html)
}

# Файлы по точному имени.
PROJECT_EXCLUDE_FILES = {
    "init_project.py",  # устаревший scaffolding-скрипт, не используется в рабочем проекте
}

# Файлы по префиксу имени.
PROJECT_EXCLUDE_FILE_PREFIXES = (
    "booking.db.bak-",  # резервные копии БД (booking.db.bak-2026-10-29 и т.п.)
)


def _is_project_excluded_path(rel_path):
    """Проверяет, попадает ли относительный путь под проектные исключения.
    Работает для папок и для файлов."""
    if not rel_path:
        return False
    rel_norm = rel_path.replace("\\", "/").strip("/")
    for p in PROJECT_EXCLUDE_PATHS:
        p_norm = p.strip("/")
        if rel_norm == p_norm or rel_norm.startswith(p_norm + "/"):
            return True
    return False


def _is_project_excluded_file(filename):
    """Проверяет имя файла по проектным исключениям."""
    if filename in PROJECT_EXCLUDE_FILES:
        return True
    for pref in PROJECT_EXCLUDE_FILE_PREFIXES:
        if filename.startswith(pref):
            return True
    return False


# ============================================================
# Остальное — универсальная логика сканера
# ============================================================

def make_output_filename(root_dir: str) -> str:
    ts = datetime.now().strftime("%d.%m.%Y_%H%M%S")
    return os.path.join(root_dir, f"{OUTPUT_PREFIX}{ts}.txt")


def safe_read_bytes(file_path):
    try:
        with open(file_path, "rb") as f:
            return f.read(), None
    except Exception as e:
        return None, str(e)


def decode_bytes(content_bytes):
    try:
        return content_bytes.decode("utf-8"), None
    except UnicodeDecodeError as e:
        try:
            text = content_bytes.decode("cp1251")
            return text, f"не UTF-8, декодировано как cp1251 (байт {e.start} некорректен в UTF-8)"
        except Exception:
            pass
        text = content_bytes.decode("utf-8", errors="replace")
        return text, f"невалидный UTF-8, невалидные байты заменены на U+FFFD (начиная с байта {e.start})"


def _filter_dirnames(dirnames, rel_dir):
    """Универсальная + проектная фильтрация папок."""
    kept = []
    for d in dirnames:
        if d in EXCLUDE_DIRS:
            continue
        d_rel = (rel_dir + "/" + d) if rel_dir else d
        if _is_project_excluded_path(d_rel):
            continue
        kept.append(d)
    return kept


def scan_project():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = make_output_filename(root_dir)
    output_name = os.path.basename(output_file)

    skipped = []
    stats = []
    project_excluded_count = 0

    with open(output_file, "w", encoding="utf-8") as out:
        out.write("=== СТРУКТУРА ПРОЕКТА ===\n")
        out.write(f"=== Дата создания дампа: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')} ===\n\n")

        # 1. Дерево
        for dirpath, dirnames, filenames in os.walk(root_dir):
            rel_dir = os.path.relpath(dirpath, root_dir)
            if rel_dir == ".":
                rel_dir = ""

            dirnames[:] = _filter_dirnames(dirnames, rel_dir)

            indent_level = 0 if not rel_dir else rel_dir.count(os.sep) + 1
            indent = "    " * indent_level
            folder_name = os.path.basename(dirpath) if rel_dir else root_dir
            out.write(f"{indent}[{folder_name}]\n")

            sub_indent = "    " * (indent_level + 1)
            for f in filenames:
                if f == output_name or f.startswith(OUTPUT_PREFIX):
                    continue
                if f in EXCLUDE_FILES:
                    continue
                if _is_project_excluded_file(f):
                    continue
                f_rel = (rel_dir + "/" + f) if rel_dir else f
                if _is_project_excluded_path(f_rel):
                    continue
                out.write(f"{sub_indent}- {f}\n")

        out.write("\n\n=== СОДЕРЖИМОЕ ФАЙЛОВ ===\n\n")

        # 2. Содержимое
        for dirpath, dirnames, filenames in os.walk(root_dir):
            rel_dir = os.path.relpath(dirpath, root_dir)
            if rel_dir == ".":
                rel_dir = ""

            dirnames[:] = _filter_dirnames(dirnames, rel_dir)

            for f in filenames:
                if f == output_name or f.startswith(OUTPUT_PREFIX):
                    continue
                if f in EXCLUDE_FILES:
                    continue

                f_rel = (rel_dir + "/" + f) if rel_dir else f

                # Проектные исключения считаем отдельно — чтобы видеть в статистике
                if _is_project_excluded_file(f) or _is_project_excluded_path(f_rel):
                    project_excluded_count += 1
                    continue

                _, ext = os.path.splitext(f)
                if ext.lower() not in INCLUDE_EXTENSIONS:
                    continue

                file_path = os.path.join(dirpath, f)

                try:
                    file_size = os.path.getsize(file_path)
                except Exception as e:
                    skipped.append((f_rel, f"не удалось получить размер: {e}"))
                    continue

                if file_size > MAX_FILE_SIZE:
                    skipped.append((
                        f_rel,
                        f"слишком большой: {file_size / 1024 / 1024:.2f} МБ "
                        f"> {MAX_FILE_SIZE / 1024 / 1024:.0f} МБ",
                    ))
                    continue

                out.write("=" * 60 + "\n")
                out.write(f"ФАЙЛ: {f_rel}  ({file_size} байт)\n")
                out.write("=" * 60 + "\n")

                content_bytes, read_error = safe_read_bytes(file_path)
                if read_error:
                    skipped.append((f_rel, f"ошибка чтения: {read_error}"))
                    out.write(f"[ОШИБКА ЧТЕНИЯ ФАЙЛА: {read_error}]\n\n\n")
                    continue

                if len(content_bytes) > HARD_LIMIT_SIZE:
                    content_bytes = content_bytes[:HARD_LIMIT_SIZE]
                    out.write(f"[!] Файл обрезан до {HARD_LIMIT_SIZE / 1024 / 1024:.0f} МБ\n")

                text, decode_note = decode_bytes(content_bytes)

                if decode_note:
                    out.write(f"[!] {decode_note}\n")

                if "\x00" in text:
                    text = text.replace("\x00", "")
                    out.write("[!] Удалены null-байты из содержимого\n")

                out.write(text)
                status = "warn" if decode_note else "ok"
                stats.append((f_rel, file_size, status))
                out.write("\n\n")

        # 3. Статистика
        out.write("\n\n=== СТАТИСТИКА ===\n\n")
        out.write(f"Всего файлов прочитано: {len(stats)}\n")
        if project_excluded_count:
            out.write(f"Отсечено проектных исключений (файлов): {project_excluded_count}\n")

        if skipped:
            out.write(f"\n⚠️  ПРОПУЩЕНО ({len(skipped)}):\n")
            for rel, reason in skipped:
                out.write(f"  - {rel}: {reason}\n")
        else:
            out.write("Пропущенных файлов нет.\n")

        warned = [s for s in stats if s[2] == "warn"]
        if warned:
            out.write(f"\n⚠️  С предупреждениями ({len(warned)}):\n")
            for rel, size, _ in warned:
                out.write(f"  - {rel} ({size} байт)\n")

        out.write("\nТоп-20 файлов по размеру:\n")
        for rel, size, status in sorted(stats, key=lambda x: -x[1])[:20]:
            out.write(f"  - {rel}: {size} байт ({status})\n")

    size_mb = os.path.getsize(output_file) / 1024 / 1024
    print(f"✅ Готово! Результат: {output_name}")
    print(f"Размер файла: {size_mb:.2f} МБ")
    if project_excluded_count:
        print(f"Отсечено проектных исключений (файлов): {project_excluded_count}")

    if skipped:
        print(f"\n⚠️  Пропущено файлов: {len(skipped)}")
        for rel, reason in skipped:
            print(f"   - {rel}: {reason}")
    else:
        print("Пропущенных файлов нет.")

    if stats:
        print(f"\nПрочитано: {len(stats)} файл(ов)")


if __name__ == "__main__":
    scan_project()
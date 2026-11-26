#!/usr/bin/env python3
"""gen_map.py — генератор PROJECT_MAP.md.

Универсальный: не зависит от структуры конкретного проекта.
Обходит дерево, извлекает сигнатуры классов/функций, docstring-и и импорты.
Результат — компактная карта, по которой AI-ассистент сразу понимает,
что где лежит, и запрашивает только нужные файлы.

Использование:
    python tools/gen_map.py
    python tools/gen_map.py --root . --output PROJECT_MAP.md
    python tools/gen_map.py --root /path/to/other-project

Требует Python 3.9+ (используется ast.unparse).
"""
import argparse
import ast
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# --- что пропускаем при обходе ---------------------------------------------
SKIP_DIRS = {
    '.git', '.hg', '.svn',
    '__pycache__', 'node_modules', 'venv', '.venv', 'env', '.env',
    'dist', 'build', '.next', '.nuxt', 'coverage', 'htmlcov',
    '.pytest_cache', '.mypy_cache', '.ruff_cache', '.tox', '.cache',
    '.idea', '.vscode',
    'static', 'staticfiles', 'media',
}
SKIP_FILE_PATTERNS = [
    r'.*\.pyc$', r'.*\.pyo$', r'.*\.so$', r'.*\.log$',
    r'.*\.min\.js$', r'.*\.min\.css$', r'.*\.map$',
]
CODE_EXT = {'.py', '.js', '.ts', '.jsx', '.tsx', '.vue', '.sh', '.bash'}
OTHER_TEXT_EXT = {'.md', '.txt', '.yml', '.yaml', '.json', '.toml',
                  '.ini', '.cfg', '.env.example', '.html', '.css'}

try:
    STDLIB = set(sys.stdlib_module_names)
except AttributeError:
    STDLIB = set()


def should_skip_file(name: str) -> bool:
    return any(re.match(pat, name) for pat in SKIP_FILE_PATTERNS)


def walk_dirs(root: Path):
    """os.walk с фильтрацией мусора и сортировкой."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in SKIP_DIRS and not d.startswith('.')
        )
        yield Path(dirpath), dirnames, sorted(filenames)


# --- парсеры ---------------------------------------------------------------
def _func_sig(node):
    args = []
    for a in node.args.args:
        ann = ''
        if a.annotation is not None:
            try:
                ann = ': ' + ast.unparse(a.annotation)
            except Exception:
                pass
        args.append(a.arg + ann)
    ret = ''
    if node.returns is not None:
        try:
            ret = ' -> ' + ast.unparse(node.returns)
        except Exception:
            pass
    prefix = 'async ' if isinstance(node, ast.AsyncFunctionDef) else ''
    return f'{prefix}def {node.name}({", ".join(args)}){ret}'


def parse_py(path: Path):
    """Возвращает (items, error). items = [(kind, name, sig, doc, line)]"""
    try:
        src = path.read_text(encoding='utf-8', errors='replace')
        tree = ast.parse(src)
    except SyntaxError as e:
        return [], f'SyntaxError: {e.msg} (line {e.lineno})'
    items = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            doc = (ast.get_docstring(node) or '').split('\n')[0].strip()
            items.append(('class', node.name, '', doc, node.lineno))
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    sdoc = (ast.get_docstring(sub) or '').split('\n')[0].strip()
                    items.append(('method', sub.name, _func_sig(sub), sdoc, sub.lineno))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = (ast.get_docstring(node) or '').split('\n')[0].strip()
            items.append(('func', node.name, _func_sig(node), doc, node.lineno))
    return items, None


def extract_imports(path: Path):
    """Внутренние и сторонние импорты (без stdlib)."""
    try:
        src = path.read_text(encoding='utf-8', errors='replace')
        tree = ast.parse(src)
    except Exception:
        return []
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                top = n.name.split('.')[0]
                if top and top not in STDLIB:
                    found.add(top)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top = node.module.split('.')[0]
                if top not in STDLIB:
                    found.add(top)
            elif node.level:
                found.add('.' * node.level)
    return sorted(found)


def parse_js_ts(path: Path):
    try:
        src = path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return [], None
    items = []
    for m in re.finditer(
        r'(?:^|\n)\s*(export\s+)?(?:async\s+)?(function|class)\s+(\w+)\s*\(([^)]*)\)',
        src,
    ):
        kind = 'class' if m.group(2) == 'class' else 'func'
        exp = 'export ' if m.group(1) else ''
        items.append((kind, m.group(3),
                      f'{exp}{m.group(2)} {m.group(3)}({m.group(4).strip()})',
                      '', src[:m.start()].count('\n') + 1))
    for m in re.finditer(
        r'(?:^|\n)\s*(export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>',
        src,
    ):
        exp = 'export ' if m.group(1) else ''
        items.append(('func', m.group(2),
                      f'{exp}const {m.group(2)} = ({m.group(3).strip()}) =>',
                      '', src[:m.start()].count('\n') + 1))
    return items, None


def analyze_file(path: Path):
    ext = path.suffix.lower()
    if ext == '.py':
        return parse_py(path)
    if ext in {'.js', '.ts', '.jsx', '.tsx', '.vue'}:
        return parse_js_ts(path)
    return [], None


def file_lines(p: Path) -> int:
    try:
        with p.open('r', encoding='utf-8', errors='replace') as fh:
            return sum(1 for _ in fh)
    except Exception:
        return 0


# --- сборка карты ----------------------------------------------------------
def build_map(root: Path) -> str:
    out = []
    out.append(f'# PROJECT MAP — {root.name}')
    out.append('')
    out.append(f'*Сгенерировано: {datetime.now().strftime("%Y-%m-%d %H:%M")}*')
    out.append('*Скрипт: `tools/gen_map.py`. Файл автогенерируемый — не редактировать вручную.*')
    out.append('')

    # 1. Дерево
    out.append('## Дерево')
    out.append('```')
    for dirpath, _dirnames, filenames in walk_dirs(root):
        rel = dirpath.relative_to(root)
        depth = 0 if rel == Path('.') else len(rel.parts)
        if rel != Path('.'):
            out.append('  ' * (depth - 1) + rel.name + '/')
        for f in filenames:
            if should_skip_file(f):
                continue
            out.append('  ' * depth + f)
    out.append('```')
    out.append('')

    # 2. Детализация
    out.append('## Файлы')
    for dirpath, _dirnames, filenames in walk_dirs(root):
        for f in filenames:
            if should_skip_file(f):
                continue
            p = dirpath / f
            rel = str(p.relative_to(root)).replace(os.sep, '/')
            ext = p.suffix.lower()
            out.append('')
            out.append(f'### `{rel}` ({file_lines(p)} стр.)')

            if ext == '.py':
                imports = extract_imports(p)
                if imports:
                    out.append(f'импорты: {", ".join("`" + i + "`" for i in imports)}')

            if ext in CODE_EXT:
                items, err = analyze_file(p)
                if err:
                    out.append(f'⚠ {err}')
                for kind, _name, sig, doc, _line in items:
                    prefix = {'class': '🏛 ', 'method': '  · ', 'func': 'ƒ '}[kind]
                    line = f'- {prefix}{sig}' if sig else f'- {prefix}**{_name}**'
                    if doc:
                        line += f' — {doc}'
                    out.append(line)
                if not items and not err:
                    out.append('_пусто / без явных объявлений_')
            elif ext in OTHER_TEXT_EXT:
                pass  # файл отмечен в дереве — этого достаточно

    out.append('')
    out.append('---')
    out.append('*Конец карты.*')
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser(description='Генератор PROJECT_MAP.md')
    ap.add_argument('--root', default='.', help='Корень проекта (по умолчанию: текущая папка)')
    ap.add_argument('--output', default=None, help='Выходной файл (по умолчанию: <root>/PROJECT_MAP.md)')
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f'[gen_map] Ошибка: {root} не папка', file=sys.stderr)
        sys.exit(1)

    output = Path(args.output) if args.output else root / 'PROJECT_MAP.md'
    text = build_map(root)
    output.write_text(text, encoding='utf-8')
    print(f'[gen_map] OK: {output} ({output.stat().st_size} байт, {text.count(chr(10)) + 1} строк)')


if __name__ == '__main__':
    main()
from __future__ import annotations

import csv
import os
import signal
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path

import pymupdf as fitz
import numpy as np
import zxingcpp

ROOT = Path(__file__).resolve().parent
IMPORT = ROOT / 'import'
RESULT = ROOT / 'result'
GS = '\x1d'
FAST_DPI = 170
RETRY_DPI = (280, 400)
WORKERS = max(1, min(6, (os.cpu_count() or 2) - 1))
CHUNK_SIZE = 12


def decode(page, dpi):
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72),
                          colorspace=fitz.csGRAY, alpha=False)
    # Buffer remains alive while zxingcpp decodes.
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    found = set()
    for symbol in zxingcpp.read_barcodes(arr, formats=zxingcpp.BarcodeFormat.DataMatrix):
        raw = getattr(symbol, 'bytes', None)
        if raw is not None:
            code = bytes(raw).decode('latin-1')
        else:
            code = symbol.text
        if code:
            found.add(code)
    return found


def process_chunk(pdf_path, start, stop):
    output = []
    with fitz.open(pdf_path) as doc:
        for idx in range(start, stop):
            try:
                page = doc[idx]
                codes = {code: FAST_DPI for code in decode(page, FAST_DPI)}
                if not codes:
                    for dpi in RETRY_DPI:
                        for code in decode(page, dpi):
                            codes.setdefault(code, dpi)
                issue = ''
                if not codes:
                    issue = 'DataMatrix не найден'
                output.append((idx + 1, codes, issue))
            except Exception as exc:
                output.append((idx + 1, {}, f'Ошибка: {exc}'))
    return output


def stop_signal(signum, frame):
    raise KeyboardInterrupt


def ctrl_z_pressed():
    """Windows: Ctrl+Z in an interactive console (Ctrl+C also works)."""
    if os.name != 'nt':
        return False
    import msvcrt
    while msvcrt.kbhit():
        key = msvcrt.getwch()
        if key == '\x1a':
            return True
        if key in ('\x00', '\xe0') and msvcrt.kbhit():
            msvcrt.getwch()
    return False


def stop_pool(pool, futures):
    for future in futures:
        future.cancel()
    # Explicitly terminate running workers so that shutdown does not hang
    # on PDF decoding currently in progress.
    workers = list(getattr(pool, '_processes', {}).values())
    for worker in workers:
        if worker.is_alive():
            worker.terminate()
    for worker in workers:
        worker.join(timeout=2)
        if worker.is_alive():
            worker.kill()
            worker.join(timeout=1)
    pool.shutdown(wait=False, cancel_futures=True)


def main():
    for folder in (IMPORT, RESULT):
        folder.mkdir(exist_ok=True)
    pdfs = sorted(IMPORT.glob('*.pdf'))
    if not pdfs:
        print('Нет PDF в папке import')
        return

    tasks = []
    total_pages = 0
    valid_pdfs = 0
    collected = []
    completed_pages = 0
    found_codes = 0
    shown_codes = 0
    pool = ProcessPoolExecutor(max_workers=WORKERS)
    interrupted = False
    try:
        for pdf in pdfs:
            if ctrl_z_pressed():
                raise KeyboardInterrupt
            try:
                with fitz.open(pdf) as doc:
                    pages = len(doc)
                total_pages += pages
                valid_pdfs += 1
                print(f'{pdf.name}: {pages} стр.', flush=True)
                for start in range(0, pages, CHUNK_SIZE):
                    stop = min(start + CHUNK_SIZE, pages)
                    tasks.append((pool.submit(process_chunk, str(pdf), start, stop), pdf.name, stop - start))
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                print(f'Ошибка открытия {pdf.name}: {exc}')

        def progress(final=False):
            ratio = completed_pages / total_pages if total_pages else 1.0
            width = 30
            filled = min(width, int(ratio * width))
            bar = '█' * filled + '░' * (width - filled)
            display_count = found_codes if final else shown_codes
            print(f'\r[{bar}] {ratio:5.1%} | {completed_pages}/{total_pages} стр. | Кодов: {display_count}    ',
                  end='\n' if final else '', flush=True)

        print()
        pending = {future: (filename, page_count) for future, filename, page_count in tasks}
        while pending:
            if ctrl_z_pressed():
                raise KeyboardInterrupt
            done, _ = wait(pending, timeout=0.2, return_when=FIRST_COMPLETED)
            for future in done:
                filename, page_count = pending.pop(future)
                try:
                    chunk = future.result()
                    for page, codes, issue in chunk:
                        collected.append((filename, page, codes, issue))
                        found_codes += len(codes)
                except Exception as exc:
                    collected.append((filename, 0, {}, f'Ошибка блока: {exc}'))
                completed_pages += page_count
                if found_codes >= shown_codes + 500:
                    shown_codes = (found_codes // 500) * 500
                progress()
        progress(final=True)
        print()
    except (KeyboardInterrupt, EOFError):
        interrupted = True
        print('\n\nОбработка прервана пользователем. Завершение процессов... ', flush=True)
        stop_pool(pool, [task[0] for task in tasks])
        print(f'Скрипт завершён. Обработано страниц: {completed_pages}/{total_pages}, '
              f'распознано кодов: {found_codes}.')
        return
    finally:
        if not interrupted:
            pool.shutdown(wait=True)

    collected.sort(key=lambda item: (item[0], item[1]))
    rows = [(filename, page, dpi, code)
            for filename, page, codes, _ in collected
            for code, dpi in sorted(codes.items())]
    problems = [(filename, page, issue)
                for filename, page, _, issue in collected if issue]
    counts = Counter(row[3] for row in rows)

    with (RESULT / 'codes.txt').open('wb') as out:
        for _, _, _, code in rows:
            out.write(code.encode('latin-1') + b'\n')
    (RESULT / 'codes_readable.txt').unlink(missing_ok=True)  # Удалить файл от прежних запусков
    with (RESULT / 'details.csv').open('w', encoding='utf-8-sig', newline='') as out:
        writer = csv.writer(out, delimiter=';')
        writer.writerow(['pdf', 'page', 'dpi', 'code_readable'])
        for filename, page, dpi, code in rows:
            writer.writerow([filename, page, dpi, code.replace(GS, '<GS>')])

    report = [
        f'PDF-файлов: {valid_pdfs}',
        f'Распознано кодов: {len(rows)}',
        f'Уникальных кодов: {len(counts)}',
        f'Повторных вхождений: {sum(n - 1 for n in counts.values() if n > 1)}',
        f'Страниц с проблемами: {len(problems)}',
        '', 'Проблемные страницы:',
        *(f'{filename}, стр. {page}: {issue}' for filename, page, issue in problems),
    ]
    (RESULT / 'report.txt').write_text('\n'.join(report) + '\n', encoding='utf-8')
    print('\n'.join(report[:5]))


if __name__ == '__main__':
    signal.signal(signal.SIGINT, stop_signal)
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, stop_signal)
    try:
        main()
    except KeyboardInterrupt:
        print('\nСкрипт прерван пользователем.')

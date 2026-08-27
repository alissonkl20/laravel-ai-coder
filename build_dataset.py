import json
import random
import re
from pathlib import Path
from xml.etree.ElementTree import iterparse

from bs4 import BeautifulSoup

MIN_SECTION_CHARS = 100
MIN_PHP_FILE_CHARS = 200
MAX_SO_EXAMPLES = 50000

HEADING_PATTERN = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)
CLASS_PATTERN = re.compile(r"\bclass\s+(\w+)")


def clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator="\n", strip=True)


def process_laravel_docs(docs_dir: Path) -> list[dict]:
    examples = []
    for md_file in docs_dir.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8", errors="ignore")
        matches = list(HEADING_PATTERN.finditer(content))
        for i, match in enumerate(matches):
            title = match.group(2).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            section = content[start:end].strip()
            if len(section) < MIN_SECTION_CHARS:
                continue
            examples.append(
                {
                    "instruction": f"Explique ou mostre como: {title}",
                    "output": section,
                }
            )
    return examples


def process_php_manual(manual_dir: Path) -> list[dict]:
    examples = []
    for html_file in manual_dir.rglob("*.html"):
        soup = BeautifulSoup(
            html_file.read_text(encoding="utf-8", errors="ignore"),
            "html.parser",
        )
        h1 = soup.find("h1")
        if not h1:
            continue
        function_name = h1.get_text(strip=True)
        if not function_name:
            continue

        parts = []
        for desc in soup.select("div.refsect1.description"):
            text = desc.get_text(separator="\n", strip=True)
            if text:
                parts.append(text)
        for example in soup.select("div.example-contents"):
            text = example.get_text(separator="\n", strip=True)
            if text:
                parts.append(text)

        if not parts:
            continue

        examples.append(
            {
                "instruction": f"Como usar a função {function_name} no PHP?",
                "output": "\n\n".join(parts),
            }
        )
    return examples


def _has_target_tag(tags: str) -> bool:
    if not tags:
        return False
    tags_lower = tags.lower()
    return "<php>" in tags_lower or "<laravel>" in tags_lower


def process_stackoverflow(posts_xml: Path) -> list[dict]:
    answers: dict[str, str] = {}
    questions: list[tuple[str, str, str]] = []

    for _, elem in iterparse(posts_xml, events=("end",)):
        if elem.tag != "row":
            elem.clear()
            continue

        post_type = elem.get("PostTypeId")
        if post_type == "2":
            post_id = elem.get("Id")
            body = elem.get("Body")
            if post_id and body:
                answers[post_id] = body
        elif post_type == "1":
            tags = elem.get("Tags") or ""
            if not _has_target_tag(tags):
                elem.clear()
                continue
            accepted_id = elem.get("AcceptedAnswerId")
            if not accepted_id:
                elem.clear()
                continue
            title = elem.get("Title") or ""
            body = elem.get("Body") or ""
            questions.append((title, body, accepted_id))

        elem.clear()

    examples = []
    for title, body, accepted_id in questions:
        answer_body = answers.get(accepted_id)
        if not answer_body:
            continue

        instruction_parts = []
        if title.strip():
            instruction_parts.append(title.strip())
        if body.strip():
            instruction_parts.append(clean_html(body))
        instruction = "\n\n".join(instruction_parts)
        output = clean_html(answer_body)

        if not instruction.strip() or not output.strip():
            continue

        examples.append({"instruction": instruction, "output": output})

    if len(examples) > MAX_SO_EXAMPLES:
        examples = random.sample(examples, MAX_SO_EXAMPLES)

    return examples


def process_laravel_source(source_dir: Path) -> list[dict]:
    examples = []
    for php_file in source_dir.rglob("*.php"):
        content = php_file.read_text(encoding="utf-8", errors="ignore")
        if len(content) < MIN_PHP_FILE_CHARS:
            continue
        match = CLASS_PATTERN.search(content)
        if not match:
            continue
        class_name = match.group(1)
        examples.append(
            {
                "instruction": (
                    f"Referência interna do framework Laravel: classe {class_name}. "
                    "Isto NÃO é uma tarefa do agent CLI. Não escreva arquivos. "
                    "Explique o código-fonte abaixo."
                ),
                "output": content,
            }
        )
    return examples


def deduplicate_by_output(examples: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique = []
    for example in examples:
        output = example["output"]
        if output in seen:
            continue
        seen.add(output)
        unique.append(example)
    return unique


def load_jsonl_recipes(path: Path) -> list[dict]:
    """Carrega exemplos curados (agent tool-calling, CRUD, auth)."""
    if not path.is_file():
        return []
    examples: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if "instruction" in record and "output" in record:
                examples.append(record)
    return examples


def rewrite_legacy_source_prompts(examples: list[dict]) -> list[dict]:
    rewritten = []
    prefix_old = "Implemente a classe "
    prefix_new = (
      "Referência interna do framework Laravel: classe "
    )
    suffix_new = (
      ". Isto NÃO é uma tarefa do agent CLI. Não escreva arquivos. "
      "Explique o código-fonte abaixo."
    )
    for example in examples:
        inst = str(example.get("instruction", ""))
        if inst.startswith(prefix_old) and "seguindo boas práticas Laravel" in inst:
            name = inst[len(prefix_old):].split(" ", 1)[0]
            example = dict(example)
            example["instruction"] = f"{prefix_new}{name}{suffix_new}"
        rewritten.append(example)
    return rewritten


def oversample_recipes(recipes: list[dict], knowledge_n: int, share: float = 0.40) -> list[dict]:
    if not recipes:
        return []
    # k * R ≈ share * (K + k * R)  →  k = share/(1-share) * K / R
    ratio = share / max(1.0 - share, 0.05)
    copies = max(8, int(ratio * knowledge_n / max(len(recipes), 1)))
    return recipes * copies


def mix_existing_dataset(base: Path) -> None:
    output_path = base / "data" / "raw_dataset.jsonl"
    recipes_path = base / "data" / "agent_recipes.jsonl"
    playbook = base / "data" / "knowledge" / "e2e_playbook.md"
    recipes = load_jsonl_recipes(recipes_path)
    if playbook.is_file():
        recipes.append(
            {
                "instruction": "Como o DRAXY implementa uma feature Laravel de ponta a ponta?",
                "output": playbook.read_text(encoding="utf-8"),
            }
        )
    existing: list[dict] = []
    if output_path.is_file():
        existing = load_jsonl_recipes(output_path)
    existing = rewrite_legacy_source_prompts(existing)
    knowledge = [
        row for row in existing
        if not str(row.get("output", "")).lstrip().startswith('{"action"')
    ]
    mixed = knowledge + oversample_recipes(recipes, len(knowledge))
    random.shuffle(mixed)
    with output_path.open("w", encoding="utf-8") as handle:
        for example in mixed:
            handle.write(json.dumps(example, ensure_ascii=False) + "\n")
    print(f"Mix: {len(mixed)} exemplos (recipes={len(recipes)}, knowledge={len(knowledge)})")
    print(f"Dataset salvo em: {output_path}")


def main() -> None:
    base = Path(__file__).parent
    import sys
    if "--mix-only" in sys.argv:
        mix_existing_dataset(base)
        return

    all_examples: list[dict] = []

    recipes_path = base / "data" / "agent_recipes.jsonl"
    recipes = load_jsonl_recipes(recipes_path)
    playbook = base / "data" / "knowledge" / "e2e_playbook.md"
    if playbook.is_file():
        recipes.append(
            {
                "instruction": "Como o DRAXY implementa uma feature Laravel de ponta a ponta?",
                "output": playbook.read_text(encoding="utf-8"),
            }
        )

    docs_dir = base / "docs-laravel"
    if docs_dir.is_dir():
        all_examples.extend(process_laravel_docs(docs_dir))

    manual_dir = base / "php_manual_en"
    if manual_dir.is_dir():
        php_examples = process_php_manual(manual_dir)
        if len(php_examples) > 2500:
            php_examples = random.sample(php_examples, 2500)
        all_examples.extend(php_examples)

    posts_xml = base / "Posts.xml"
    if posts_xml.is_file():
        all_examples.extend(process_stackoverflow(posts_xml))

    source_dir = base / "laravel_source"
    if source_dir.is_dir():
        source_examples = process_laravel_source(source_dir)
        if len(source_examples) > 800:
            source_examples = random.sample(source_examples, 800)
        all_examples.extend(source_examples)

    all_examples = deduplicate_by_output(all_examples)
    all_examples.extend(oversample_recipes(recipes, len(all_examples)))
    random.shuffle(all_examples)

    output_path = base / "data" / "raw_dataset.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for example in all_examples:
            f.write(json.dumps(example, ensure_ascii=False) + "\n")

    print(f"Total de exemplos: {len(all_examples)}")
    print(f"Dataset salvo em: {output_path}")


if __name__ == "__main__":
    main()

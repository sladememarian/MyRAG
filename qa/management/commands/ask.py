"""Ask a question from the terminal, without the admin or the API."""
from django.core.management.base import BaseCommand, CommandError

from rag.chain import answer_question
from rag.errors import RAGError


class Command(BaseCommand):
    help = 'Ask a question against the indexed documents: python manage.py ask "..."'

    def add_arguments(self, parser):
        parser.add_argument("question", nargs="+", help="The question to ask")

    def handle(self, *args, **options):
        question = " ".join(options["question"]).strip()
        self.stdout.write(f"Question: {question}\n")

        try:
            result = answer_question(question)
        except RAGError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS("\nAnswer:"))
        self.stdout.write(result["answer"])
        self.stdout.write("\nSources:")
        if not result["sources"]:
            self.stdout.write("  (none)")
        for index, source in enumerate(result["sources"], start=1):
            self.stdout.write(
                f"  [{index}] {source['title']} "
                f"(document {source['document_id']}, chunk {source['chunk_index']}, "
                f"score {source['score']})"
            )
            self.stdout.write(f"      {source['snippet']}")

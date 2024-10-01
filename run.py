import statsliggaren as sl
from services.writer import Writer
from markdownify import markdownify as md

rbids = [i for i in range(24800)]
metadata, attachments, letters = sl.get_metadatas(rbids)

Writer.write_csv(metadata, "letters.csv")
Writer.write_csv(attachments, "attachments.csv")

for rbid in letters:
    letter = letters[rbid]
    if letter:
        Writer.write_text(letters[rbid], f"letters/html/{rbid}.html")
        Writer.write_text(md(letters[rbid]), f"letters/md/{rbid}.md")

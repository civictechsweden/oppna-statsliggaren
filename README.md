# Öppna Statsliggaren

This project aims at making the Swedish agencies mission letters (*regleringsbrev*) more accessible through a simple API and a dataset on HuggingFace.

Today, mission letters are made available on a web application called [*Statsliggaren*](https://www.statskontoret.se/statsliggaren) on the website of the [Agency for Financial and Public Management](https://www.statskontoret.se/english/) (*Statskontoret*, formerly *Ekonomistyrningsverket*). Discloser: They are my employer as of 2026 but this is an unrelated side-project.

It is hard to download the mission letter for a specific agency and a specific year from there as every document is given an obscure ID that gets incremented with each new document.

So this project essentially maps the IDs to these metadata, enabling someone to download what they need without scraping the website.

## Usage

For now, it's best to download the file [letters.csv](letters.csv) and process it yourself to match an agency and a year to a file ID.

You can also download the file [attachments.csv](attachments.csv) to get a list of the letters' attachments.

### Optional IP rotation

In order to fetch with a Github Action, we need to use a EU proxy. Right now, the program uses AWS API Gateway which has a large free tier.

You will not have to use it locally but if you want to you will need working AWS credentials in `.env`:

```text
USE_IP_ROTATOR=true
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
```

### Download a file with its ID

You can access a mission letter's page through this URL:

```text
https://www.statskontoret.se/statsliggaren/regleringsbrev/index?RbId={ID}
```

If a PDF version is available, you can download it at this URL:

```text
https://www.statskontoret.se/regleringsbrev/{ID}/pdf
```

If you just want the changes, you can add the parameter *version=EndastAndringar*:

```text
https://www.statskontoret.se/statsliggaren/regleringsbrev/index?RbId={ID}&version=EndastAndringar
https://www.statskontoret.se/regleringsbrev/{ID}/pdf?Version=EndastAndringar
```

Attachments are only available as files and can be downloaded at the following URL:

```text
https://www.statskontoret.se/regleringsbrev/bilaga/{ID}
```

### Parquet export

The repository can also build a Parquet export with four columns: `id`, `html`, `xhtml`, and `md`.
Run it locally with:

```bash
uv run python scripts/build_letters_parquet.py --output letters.parquet
```

If you want to upload the result to Hugging Face, set `HF_TOKEN` and pass a dataset repo id:

```bash
HF_TOKEN=... uv run python scripts/build_letters_parquet.py --output letters.parquet --repo-id your-org/your-dataset --repo-path data/letters.parquet
```

If the local Parquet file does not exist but a Hugging Face dataset repo is configured, the script first downloads the existing remote Parquet file and then appends only the locally missing ids before uploading the refreshed file again.

The nightly GitHub Action also updates the Hugging Face dataset after refreshing `letters.csv` and `attachments.csv`. To enable that, set:

- `HF_DATASET_REPO_ID` as a GitHub Actions variable
- `HF_TOKEN` as a GitHub Actions secret

## Future developments

Running the code in its current state will also download the HTML letters and attempt a conversion to Markdown. In the future, a more complex processing will be added to convert the letters to a clean reusable format and upload them to HuggingFace.

## License

License for the data is CC0, as the files are public documents (*offentliga handlingar*).

License for the code is AGPLv3.

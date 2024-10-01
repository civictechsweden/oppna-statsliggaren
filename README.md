# Öppna Statsliggaren

This project aims at making the Swedish agencies mission letters (*regleringsbrev*) more accessible through a simple API and a dataset on HuggingFace.

Today, mission letters are made available on a web application called [*Statsliggaren*](https://www.esv.se/statsliggaren) on the website of the [Swedish National Financial Management Authority](https://www.esv.se/english/)(*Ekonomistyrningsverket*). Discloser: They are my employer as of 2024 but this is an unrelated side-project.

It is hard to download the mission letter for a specific agency and a specific year from there as every document is given an obscure ID that gets incremented with each new document.

So this project essentially maps the IDs to these metadata, enabling someone to download what they need without scraping the website.

## Usage

For now, it's best to download the file [letters.csv](letters.csv) and process it yourself to match an agency and a year to a file ID.

You can also download the file [attachments.csv](attachments.csv) to get a list of the letters' attachments.

### Download a file with its ID

You can access a mission letter's page through this URL:

```text
https://www.esv.se/statsliggaren/regleringsbrev/Index?rbId={ID}
```

If a PDF version is available, you can download it at this URL:

```text
https://www.esv.se/Regleringsbrev/Pdf?RbId={ID}
```

If you just want the changes, you can add the parameter *version=EndastAndringar*:

```text
https://www.esv.se/statsliggaren/regleringsbrev/Index?rbId={ID}&version=EndastAndringar
https://www.esv.se/Regleringsbrev/Pdf?RbId={ID}&version=EndastAndringar
```

Attachments are only available as files and can be downloaded at the following URL:

```text
https://www.esv.se/Regleringsbrev/Bilaga?BilageID={ID}
```

## Future developments

Running the code in its current state will also download the HTML letters and attempt a conversion to Markdown. In the future, a more complex processing will be added to convert the letters to a clean reusable format and upload them to HuggingFace.

## License

License for the data is CC0, as the files are public documents (*offentliga handlingar*).

License for the code is AGPLv3.

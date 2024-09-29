# Öppna statsliggaren

This project aims at making the Swedish agencies mission letters (*regleringsbrev*) more accessible through a simple API and a dataset on HuggingFace.

Today, mission letters are made available on a web application called [*Statsliggaren*](https://www.esv.se/statsliggaren) on the website of the [Swedish National Financial Management Authority](https://www.esv.se/english/)(*Ekonomistyrningsverket*).Discloser: They are my employer as of 2024 but this is an unrelated side-project.

It is hard to download the mission letter for a specific agency and a specific year from there as every document is given an obscure ID that gets incremented with each new document.

So this project essentially maps the IDs to these metadata, enabling someone to download what they need without scraping the website.

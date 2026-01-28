## Usage
Start a new instance of the Data Analytics Assistant using:
```
http://localhost:8052
```
Queries can be entered in the lower right chat input area.  Once a  final answer is output you will be able to view the intermediate tool steps.  You can also run an independent audit of the final answer.

![assistant screen](.\assistant screen.png)

The demo database is loaded from surveys on Social Determinants of Health (SDoH) from the [Agency for Healthcare Research and Quality](https://www.ahrq.gov/sdoh/data-analytics/sdoh-data.html). Metrics are provided by county, state and year (2017 - 2020).  You can [download data and codebooks](https://www.ahrq.gov/sdoh/data-analytics/sdoh-data.html#download) and documentation on [data sources](https://www.ahrq.gov/sites/default/files/wysiwyg/sdoh/SDOH-Data-Sources-Documentation-v1-Final.pdf) is available. You can ask the assistant to find metrics using descriptions.  Note that only columns that apply to SDoH are loaded.  You can use the CSV file at **da-assistant/etl-notebooks/dictionary.csv** as a reference.

Note that the demo database has about 500 columns and 10K rows.  Requests that produce a large number of columns or rows will result in large prompts to the LLM which could exceed rate limits.  This may result in the request being rejected.  For instance, this prompt:
```
show the  number of storm events by state, county and year
```
gives error:
```
An error occurred: Error code: 429 - {'error': {'message': 'Request too large for gpt-4o in organization org-ecUAqz on tokens per min (TPM): Limit 30000, Requested 129625. The input or output tokens must be reduced in order to run successfully.

```
Reduce token usage by aggregating or filtering, e.g.:
```

show the state, county, year and average number of storm events for the state of Ohio.

```
You can also review and run the ETL notebooks. To start an instance of JupyterLab:
```
http://localhost:8888
```
The notebook ***notebooks/load_database.ipynb** downloads, cleans and filters survey data and loads the database.  It also downloads the survey codebook to load the data dictionary.
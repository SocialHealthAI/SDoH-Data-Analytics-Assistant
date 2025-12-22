## Usage
Start a new instance of the Data Analytics Assistant using:
```
http://localhost:8052
```
The assistant starts with a default prompt describing its capabilities.  When entering a prompt, use **Ctrl+Enter** to send the request.  The assistant shows the intermediate steps and the final answer.

After the final answer you can run the Audit Assistant to review the process and final answer.  Select the **Run Audit** button.

The demo database is loaded from surveys on Social Determinants of Health (SDOH) from the [Agency for Healthcare Research and Quality](https://www.ahrq.gov/sdoh/data-analytics/sdoh-data.html). Metrics are provided by county, state and year (2017 - 2020).  You can [download data and codebooks](https://www.ahrq.gov/sdoh/data-analytics/sdoh-data.html#download) and documentation on [data sources](https://www.ahrq.gov/sites/default/files/wysiwyg/sdoh/SDOH-Data-Sources-Documentation-v1-Final.pdf) is available. You can ask the assistant to find metrics using descriptions.  Note that only columns that apply to SDOH are loaded.  You can use the CSV file at **da-assistant/etl-notebooks/dictionary.csv** as a reference.

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
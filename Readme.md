# This is a WebScraping Tool 

## Install the necessary dependencies
**Make sure to have the latest version of python**

```
pip install python3 
pip install requests
pip install pandas
```

## Get your SERPER_API_KEY 
```
- Go to serper.dev to get your api key (lots of free credits)
- if on zsh: export SERPER_API_KEY = "your_api_key_here"
- if on powershell: $env:SERPER_API_KEY = "your_api_key_here"

```

## It has a very simple layout: 

```

data : has all the necessary input and output files 
main_scaper.py: you run this file to generate the necessary information of companies
- if on zsh: python3 main_scraper.py
- if on powershell: python main_scraper.py

```

## HOW TO INPUT FILES

```
simply write your csv file name in this line: 
df = pd.read_csv("data/clothes_data.csv")

```

## Decide your output file name 

```
simple write your output file name here, and it will be populated 
df_results.to_csv("data/clothes_phone.csv", index=False)
**make sure not to have the csv open when running the code**
```

**Note**: This tool is designed for legitimate business contact information gathering.
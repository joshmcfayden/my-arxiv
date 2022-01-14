# my-arxiv
Personalised daily emails with new papers from [arxiv.org](https://arxiv.org/) with "nice" formatting!

Mainly taken from https://github.com/karpathy/arxiv-sanity-preserver

Choose your arXiv API search query and add filter terms to highlight. Sends daily summary email using gmail SMTP.

Needs daily cron job with crontab entry like:
```bash
30 8 * * * /Users/$USER/my-arxiv/fetch_papers.py >& /Users/$USER/my-arxiv/fetch_papers.log
```
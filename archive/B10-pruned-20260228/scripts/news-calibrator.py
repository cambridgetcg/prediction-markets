#!/usr/bin/env python3
"""
News Calibrator — Fetches domain news via RSS, matches to active markets/positions,
and uses Claude to generate updated probability estimates.

Usage:
    python3 scripts/news-calibrator.py                        # All domains, last 12h
    python3 scripts/news-calibrator.py --domain GEO            # Single domain
    python3 scripts/news-calibrator.py --hours 4               # Shorter lookback
    python3 scripts/news-calibrator.py --positions-only        # Only news matching held positions
    python3 scripts/news-calibrator.py --no-ai                 # Just show news feed, skip Claude
    python3 scripts/news-calibrator.py --dry-run               # Show Claude prompt, don't call API
    python3 scripts/news-calibrator.py --json                  # Machine-readable output
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# --- Dependency check ---

_MISSING = []
try:
    import feedparser
except ImportError:
    _MISSING.append('feedparser')

try:
    import requests
except ImportError:
    _MISSING.append('requests')

try:
    import anthropic
except ImportError:
    _MISSING.append('anthropic')

if _MISSING:
    print(f"Missing dependencies: {', '.join(_MISSING)}")
    print(f"Install with: pip3 install {' '.join(_MISSING)}")
    sys.exit(1)

# --- Paths ---

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / 'data'
DOMAINS_DIR = PROJECT_DIR / 'domains'
POSITIONS_FILE = PROJECT_DIR / 'strategies' / 'paper-trades' / 'positions.json'
CREDIBILITY_FILE = PROJECT_DIR / 'sources' / 'credibility-matrix.json'
SEEN_FILE = DATA_DIR / 'news-calibrator-seen.json'
LOG_FILE = DATA_DIR / 'news-calibration-log.jsonl'

# --- RSS Feed Configuration ---

FEEDS = {
    'GEO': [
        ('Reuters World', 'https://feeds.reuters.com/Reuters/worldNews'),
        ('AP World', 'https://rsshub.app/apnews/topics/world-news'),
        ('BBC World', 'https://feeds.bbci.co.uk/news/world/rss.xml'),
        ('Al Jazeera', 'https://www.aljazeera.com/xml/rss/all.xml'),
    ],
    'POL': [
        ('Politico', 'https://rss.politico.com/politics-news.xml'),
        ('The Hill', 'https://thehill.com/feed/'),
        ('AP Politics', 'https://rsshub.app/apnews/topics/politics'),
        ('Reuters Politics', 'https://feeds.reuters.com/Reuters/PoliticsNews'),
    ],
    'ECO': [
        ('Reuters Business', 'https://feeds.reuters.com/reuters/businessNews'),
        ('CNBC Economy', 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258'),
        ('FT', 'https://www.ft.com/?format=rss'),
    ],
    'CRY': [
        ('CoinDesk', 'https://www.coindesk.com/arc/outboundfeeds/rss/'),
        ('The Block', 'https://www.theblock.co/rss.xml'),
        ('Decrypt', 'https://decrypt.co/feed'),
        ('CoinTelegraph', 'https://cointelegraph.com/rss'),
    ],
    'TEC': [
        ('Ars Technica', 'https://feeds.arstechnica.com/arstechnica/index'),
        ('The Verge', 'https://www.theverge.com/rss/index.xml'),
        ('TechCrunch AI', 'https://techcrunch.com/category/artificial-intelligence/feed/'),
    ],
    'LAW': [
        ('SCOTUSblog', 'https://www.scotusblog.com/feed/'),
        ('Reuters Legal', 'https://feeds.reuters.com/reuters/domesticNews'),
        ('Courthouse News', 'https://www.courthousenews.com/feed/'),
    ],
    'ENV': [
        ('BBC Environment', 'https://feeds.bbci.co.uk/news/science_and_environment/rss.xml'),
        ('Guardian Environment', 'https://www.theguardian.com/environment/rss'),
        ('Carbon Brief', 'https://www.carbonbrief.org/feed/'),
    ],
    'FIN': [
        ('CNBC Markets', 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069'),
        ('Reuters Business', 'https://feeds.reuters.com/reuters/businessNews'),
        ('Yahoo Finance', 'https://finance.yahoo.com/news/rssindex'),
    ],
    'SCI': [
        ('Nature', 'https://www.nature.com/nature.rss'),
        ('Science', 'https://www.science.org/rss/news_current.xml'),
        ('Space News', 'https://spacenews.com/feed/'),
    ],
    'SOC': [
        ('AP Entertainment', 'https://rsshub.app/apnews/topics/entertainment'),
        ('Variety', 'https://variety.com/feed/'),
    ],
}

GOOGLE_NEWS_RSS = 'https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en'

# Reuse domain keywords from spike-detector.py
DOMAIN_KEYWORDS = {
    'GEO': ['iran', 'strike', 'war', 'invasion', 'ceasefire', 'nato', 'ukraine',
             'russia', 'china', 'taiwan', 'israel', 'lebanon', 'khamenei',
             'regime', 'leader out', 'prime minister', 'grenell', 'venezuela',
             'greenland', 'annex', 'invade', 'maduro', 'nuclear', 'sanctions',
             'missile', 'military', 'troops', 'diplomat', 'geneva'],
    'CRY': ['bitcoin', 'btc', 'ethereum', 'eth', 'solana', 'sol', 'xrp',
             'crypto', 'token', 'fdv', 'launch', 'dip to', 'reach $',
             'stablecoin', 'defi', 'mining'],
    'POL': ['president', 'nomination', 'democrat', 'republican', 'trump',
             'election', 'nominate', 'congress', 'senate', 'governor',
             'fed chair', 'speaker', 'vance', 'newsom', 'desantis', 'gop'],
    'ECO': ['fed ', 'interest rate', 'bps', 'gdp', 'inflation', 'cpi',
             'unemployment', 'revenue', 'treasury', 'fomc', 'rate cut',
             'rate hike', 'labor market', 'jobs report', 'pce'],
    'TEC': ['ai model', 'anthropic', 'openai', 'google', 'chatgpt', 'claude',
             'gemini', 'gpt', 'artificial intelligence', 'machine learning',
             'benchmark', 'agi'],
    'LAW': ['supreme court', 'scotus', 'ruling', 'lawsuit', 'indictment',
             'verdict', 'appeal', 'regulation', 'antitrust', 'sec '],
    'ENV': ['earthquake', 'hurricane', 'snow', 'temperature', 'wildfire',
             'climate', 'storm', 'emissions', 'carbon', 'drought'],
    'FIN': ['stock market', 'dow', 'nasdaq', 's&p', 'earnings', 'ipo',
             'merger', 'acquisition', 'rally', 'sell-off'],
    'SCI': ['space', 'nasa', 'rocket', 'satellite', 'mars', 'moon',
             'research', 'discovery', 'physics', 'biology'],
    'SOC': ['entertainment', 'movie', 'music', 'celebrity', 'oscar',
             'grammy', 'emmy', 'streaming', 'box office'],
}

DEFAULT_MODEL = 'claude-sonnet-4-20250514'

# --- Credibility ---

def load_credibility_matrix():
    """Load source credibility scores from credibility-matrix.json."""
    if not CREDIBILITY_FILE.exists():
        return {}
    try:
        with open(CREDIBILITY_FILE) as f:
            sources = json.load(f)
        return {s['source'].lower(): s for s in sources}
    except (json.JSONDecodeError, KeyError):
        return {}


def get_credibility_score(source_name, cred_matrix):
    """Look up composite credibility score for a source. Returns (score, source_key)."""
    name_lower = source_name.lower()
    for key, data in cred_matrix.items():
        if key in name_lower or name_lower in key:
            return data.get('composite_score', 3.0), key
    # Check partial matches (e.g., "Reuters" in "Reuters World")
    for key, data in cred_matrix.items():
        first_word = key.split()[0]
        if first_word in name_lower or name_lower.startswith(first_word):
            return data.get('composite_score', 3.0), key
    return 3.0, None  # Default score


# --- Deduplication ---

def load_seen(no_dedup=False):
    """Load seen news items hash set."""
    if no_dedup or not SEEN_FILE.exists():
        return {}
    try:
        with open(SEEN_FILE) as f:
            seen = json.load(f)
        # Prune entries older than 7 days
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        return {k: v for k, v in seen.items() if v > cutoff}
    except (json.JSONDecodeError, ValueError):
        return {}


def save_seen(seen):
    """Save seen news items."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SEEN_FILE, 'w') as f:
        json.dump(seen, f, indent=2)


def news_hash(source, title):
    """Create a hash for deduplication."""
    key = f"{source}|{title}".lower().strip()
    return hashlib.sha256(key.encode()).hexdigest()[:16]


# --- News Fetching ---

def fetch_rss(feed_name, feed_url, hours, timeout=15):
    """Fetch and parse an RSS feed. Returns list of news items."""
    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    try:
        resp = requests.get(feed_url, timeout=timeout, headers={
            'User-Agent': 'PredictionMarkets-NewsCalibrator/1.0'
        })
        if resp.status_code != 200:
            return items
        feed = feedparser.parse(resp.text)
    except (requests.RequestException, Exception):
        return items

    for entry in feed.entries:
        # Parse published date
        published = None
        for date_field in ['published_parsed', 'updated_parsed']:
            dt = entry.get(date_field)
            if dt:
                try:
                    published = datetime(*dt[:6], tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    pass
                break

        # If no date, use current time (include it, let dedup filter)
        if published is None:
            published = datetime.now(timezone.utc)

        if published < cutoff:
            continue

        title = entry.get('title', '').strip()
        if not title:
            continue

        summary = entry.get('summary', entry.get('description', '')).strip()
        # Strip HTML tags from summary
        summary = re.sub(r'<[^>]+>', '', summary)
        # Truncate long summaries
        if len(summary) > 300:
            summary = summary[:297] + '...'

        link = entry.get('link', '')

        items.append({
            'source': feed_name,
            'title': title,
            'summary': summary,
            'link': link,
            'published': published.isoformat(),
            'published_dt': published,
        })

    return items


def fetch_google_news(query, hours, timeout=15):
    """Fetch Google News RSS as fallback."""
    url = GOOGLE_NEWS_RSS.format(query=requests.utils.quote(query))
    return fetch_rss(f'Google News ({query})', url, hours, timeout)


def fetch_domain_news(domain, hours, verbose=False):
    """Fetch all news for a domain from configured feeds + Google News fallback."""
    all_items = []

    feeds = FEEDS.get(domain, [])
    for feed_name, feed_url in feeds:
        if verbose:
            print(f"  Fetching {feed_name}...", end='', flush=True)
        items = fetch_rss(feed_name, feed_url, hours)
        if verbose:
            print(f" {len(items)} items")
        all_items.extend(items)
        time.sleep(0.1)  # Be polite

    # Google News fallback if few items
    if len(all_items) < 3:
        keywords = DOMAIN_KEYWORDS.get(domain, [])
        if keywords:
            query = ' OR '.join(keywords[:5])
            if verbose:
                print(f"  Fetching Google News fallback...", end='', flush=True)
            gn_items = fetch_google_news(query, hours)
            if verbose:
                print(f" {len(gn_items)} items")
            all_items.extend(gn_items)

    # Sort by published date, newest first
    all_items.sort(key=lambda x: x.get('published', ''), reverse=True)
    return all_items


# --- Market Matching ---

def load_positions():
    """Load active positions from positions.json."""
    if not POSITIONS_FILE.exists():
        return []
    try:
        with open(POSITIONS_FILE) as f:
            data = json.load(f)
        return [p for p in data.get('positions', []) if p.get('status') == 'open']
    except (json.JSONDecodeError, KeyError):
        return []


def extract_keywords_from_market(market_name):
    """Extract meaningful keywords from a market name."""
    # Remove common words
    stop_words = {'will', 'the', 'by', 'in', 'of', 'a', 'an', 'be', 'to', 'or',
                  'and', 'is', 'at', 'for', 'on', 'with', 'from', 'this', 'that',
                  'not', 'no', 'yes', 'if', 'end', 'before', 'after', 'has', 'have',
                  'does', 'do', 'did', 'was', 'were', 'been', 'being'}
    words = re.findall(r'[A-Za-z]+(?:\'[A-Za-z]+)?', market_name)
    keywords = []
    for w in words:
        if w.lower() not in stop_words and len(w) > 2:
            keywords.append(w.lower())

    # Extract dollar amounts only — dates and years are too generic
    amounts = re.findall(r'\$[\d,]+', market_name)
    keywords.extend(amounts)

    return keywords


def parse_active_md(domain):
    """Parse active.md for a domain. Returns list of tracked markets."""
    active_file = DOMAINS_DIR / domain / 'active.md'
    if not active_file.exists():
        return []

    markets = []
    try:
        with open(active_file) as f:
            content = f.read()
    except IOError:
        return []

    # Extract market names from headers and table rows
    # Headers like "## US Strikes Iran"
    # Section headers that are NOT market names
    skip_headers = {'active position', 'next market', 'recommended paper trade',
                    'recommended trade', 'markets to watch', 'reasoning',
                    'key date', 'key finding', 'top 3', 'notes', 'summary',
                    'calibration', 'research', 'new market'}

    for match in re.finditer(r'^##\s+(.+)$', content, re.MULTILINE):
        title = match.group(1).strip()
        if not title:
            continue
        title_lower = title.lower()
        if any(skip in title_lower for skip in skip_headers):
            continue
        keywords = extract_keywords_from_market(title)
        if len(keywords) >= 2:
            markets.append({
                'title': title,
                'domain': domain,
                'keywords': keywords,
                'source': 'active.md',
            })

    # Table rows with market names (look for pipe-separated rows with market-like content)
    # Only match rows that look like actual market questions, not candidate names or parameters
    for match in re.finditer(r'^\|\s*(.+?)\s*\|.*\|.*\|', content, re.MULTILINE):
        cell = match.group(1).strip()
        # Skip headers, separators, and short entries (candidate names, IDs, etc.)
        if cell.startswith('-') or cell.startswith('=') or cell.startswith('*'):
            continue
        skip_labels = ('Market', 'Timeframe', 'Target', 'Candidate', 'ID', 'Parameter',
                       'Position', 'Entry', 'Value', 'Notes')
        if cell in skip_labels:
            continue
        # Must be descriptive enough to be a market (e.g., "US-Iran nuclear deal by Jun 30")
        # Skip short candidate names, simple labels, and parameter-like rows
        if len(cell) > 20 and not cell.startswith('|'):
            cell_lower = cell.lower()
            # Skip rows that are clearly not market names
            if any(w in cell_lower for w in ('expected', 'payout', 'horizon', 'hold to',
                                              'time horizon', 'entry', 'parameter',
                                              'recommendation', 'verdict')):
                continue
            keywords = extract_keywords_from_market(cell)
            if len(keywords) >= 3:
                markets.append({
                    'title': cell,
                    'domain': domain,
                    'keywords': keywords,
                    'source': 'active.md',
                })

    return markets


# Words that are common in news text but don't indicate market-specific relevance
_GENERIC_WORDS = frozenset([
    'strike', 'leader', 'regime', 'military', 'troops', 'price', 'reach',
    'before', 'after', 'model', 'released', 'record', 'global', 'world',
    'first', 'second', 'third', 'report', 'study', 'level', 'levels',
    'about', 'their', 'there', 'would', 'could', 'should', 'other',
    'which', 'where', 'while', 'every', 'still', 'under', 'since',
    'january', 'february', 'march', 'april', 'june', 'july',
    'august', 'september', 'october', 'november', 'december',
    'trial', 'election', 'happen', 'state', 'union', 'address',
    'control', 'style', 'count', 'tweet', 'governor',
])


def _keyword_match_score(keywords, text):
    """Score how well keywords match text. Returns (score, matched_keywords).
    Requires entity-level keywords (>4 chars) to anchor the match, not just
    generic short words like 'strike', 'leader', 'regime'."""
    matched = []
    entity_match = False  # At least one proper noun / entity keyword

    for kw in keywords:
        if kw in text:
            matched.append(kw)
            # Proper nouns / entities are >4 chars and not generic action words
            if len(kw) > 4 and kw not in _GENERIC_WORDS:
                entity_match = True

    score = len(matched)
    return score, matched, entity_match


def match_news_to_markets(news_items, positions, active_markets):
    """Match news items to positions and active markets. Returns enriched news items."""
    for item in news_items:
        text = (item['title'] + ' ' + item.get('summary', '')).lower()
        item['matched_positions'] = []
        item['matched_markets'] = []
        item['relevance_score'] = 0

        # Match against positions (highest priority)
        for pos in positions:
            pos_keywords = extract_keywords_from_market(pos['market'])
            score, matched, entity_match = _keyword_match_score(pos_keywords, text)
            # Require: (2+ matches AND at least one entity) OR (3+ matches)
            if (score >= 2 and entity_match) or score >= 3:
                item['matched_positions'].append({
                    'trade_id': pos['trade_id'],
                    'market': pos['market'],
                    'direction': pos['direction'],
                    'match_score': score,
                })
                item['relevance_score'] += 10 + score * 2

        # Match against active markets
        for market in active_markets:
            score, matched, entity_match = _keyword_match_score(market['keywords'], text)
            if (score >= 2 and entity_match) or score >= 3:
                # Avoid duplicating position matches
                already = any(m['market'] == market['title'] for m in item['matched_positions'])
                if not already:
                    item['matched_markets'].append({
                        'title': market['title'],
                        'domain': market['domain'],
                        'match_score': score,
                    })
                    item['relevance_score'] += 5 + score

        # Domain keyword match (lowest priority)
        if not item['matched_positions'] and not item['matched_markets']:
            for domain, keywords in DOMAIN_KEYWORDS.items():
                domain_matches = sum(1 for kw in keywords if kw in text)
                if domain_matches >= 2:
                    item['relevance_score'] += domain_matches
                    break

    return news_items


# --- AI Calibration ---

def get_api_key():
    """Get Anthropic API key from env or macOS Keychain."""
    key = os.environ.get('ANTHROPIC_API_KEY')
    if key:
        return key

    # Try macOS Keychain
    try:
        result = subprocess.run(
            ['security', 'find-generic-password', '-a', 'prediction-markets',
             '-s', 'anthropic_api_key', '-w'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass

    return None


def build_calibration_prompt(news_items, positions, active_markets, domain_filter=None):
    """Build the prompt for Claude calibration."""
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    parts = [
        f"You are a prediction market calibration assistant. Today is {today}.",
        "",
        "I'm going to give you recent news items matched to my active prediction market positions and tracked markets.",
        "For each affected market, provide an updated probability estimate based on the news.",
        "",
        "Base rates to keep in mind:",
        "- 73.5% of 'by date' markets resolve NO overall",
        "- Domain NO rates: ENV 82.4%, POL 78.3%, CRY 69.5%, GEO 64.3%, TEC 63.6%, ECO 60.0%",
        "- ~40% reversion within 7 days after 5pp shock",
        "",
    ]

    # Current positions
    if positions:
        parts.append("## MY ACTIVE POSITIONS")
        parts.append("")
        for pos in positions:
            if domain_filter and pos.get('domain') != domain_filter:
                continue
            parts.append(f"- **{pos['trade_id']}** ({pos['strategy']}) {pos['market']}")
            parts.append(f"  Direction: {pos['direction']} | Entry: ${pos['entry_price']} | Current: ${pos['current_price']}")
            if pos.get('exit_rules'):
                rules = pos['exit_rules']
                parts.append(f"  Exit rules: {json.dumps(rules)}")
            parts.append(f"  Resolution: {pos.get('resolution_date', 'N/A')}")
            parts.append("")

    # Active markets from domains
    if active_markets:
        parts.append("## TRACKED MARKETS")
        parts.append("")
        seen_titles = set()
        for m in active_markets:
            if domain_filter and m.get('domain') != domain_filter:
                continue
            if m['title'] not in seen_titles:
                parts.append(f"- [{m['domain']}] {m['title']}")
                seen_titles.add(m['title'])
        parts.append("")

    # News items
    matched_news = [n for n in news_items if n['relevance_score'] > 0]
    matched_news.sort(key=lambda x: x['relevance_score'], reverse=True)

    if matched_news:
        parts.append(f"## RECENT NEWS ({len(matched_news)} items matched)")
        parts.append("")
        for i, item in enumerate(matched_news[:25]):  # Cap at 25
            cred_str = f" (credibility: {item.get('credibility_score', 'N/A')}/5)" if item.get('credibility_score') else ""
            age = _format_age(item.get('published_dt'))
            parts.append(f"{i+1}. **[{item['source']}]**{cred_str} — {age}")
            parts.append(f"   {item['title']}")
            if item.get('summary'):
                parts.append(f"   > {item['summary'][:200]}")
            if item['matched_positions']:
                for mp in item['matched_positions']:
                    parts.append(f"   -> Position {mp['trade_id']}: {mp['market']}")
            if item['matched_markets']:
                for mm in item['matched_markets']:
                    parts.append(f"   -> Tracked: {mm['title']}")
            parts.append("")

    # Response format
    parts.append("## INSTRUCTIONS")
    parts.append("")
    parts.append("Respond with a JSON array. For each market affected by the news:")
    parts.append('```json')
    parts.append('[')
    parts.append('  {')
    parts.append('    "market": "market name",')
    parts.append('    "trade_id": "T001 or null if no position",')
    parts.append('    "previous_estimate": "55-62% YES",')
    parts.append('    "updated_estimate": "53-58% YES",')
    parts.append('    "delta_pp": -3,')
    parts.append('    "confidence": "HIGH|MEDIUM|LOW",')
    parts.append('    "reasoning": "One sentence explaining the update."')
    parts.append('  }')
    parts.append(']')
    parts.append('```')
    parts.append("")
    parts.append("If no news meaningfully affects a market, omit it from the array.")
    parts.append("If no markets are affected at all, return an empty array [].")
    parts.append("Focus on NEWS that changes probabilities, not noise.")

    return '\n'.join(parts)


def _format_age(dt):
    """Format a datetime as a human-readable age string."""
    if not dt:
        return 'unknown'
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return 'unknown'
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    hours = delta.total_seconds() / 3600
    if hours < 1:
        mins = int(delta.total_seconds() / 60)
        return f"{mins}m ago"
    elif hours < 24:
        return f"{hours:.0f}h ago"
    else:
        days = int(hours / 24)
        return f"{days}d ago"


def call_claude(prompt, model=DEFAULT_MODEL):
    """Call Claude API and return parsed calibration response."""
    api_key = get_api_key()
    if not api_key:
        print("ERROR: No Anthropic API key found.")
        print("Set ANTHROPIC_API_KEY env var or store in macOS Keychain:")
        print('  security add-generic-password -a prediction-markets -s anthropic_api_key -w "sk-ant-..."')
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=2000,
            messages=[{'role': 'user', 'content': prompt}],
        )
    except anthropic.APIError as e:
        print(f"ERROR: Claude API call failed: {e}")
        return None, 0, 0

    text = response.content[0].text
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens

    # Parse JSON from response (may be wrapped in ```json ... ```)
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_str = text

    try:
        updates = json.loads(json_str)
        if not isinstance(updates, list):
            updates = [updates]
    except json.JSONDecodeError:
        # Try to find JSON array in text
        arr_match = re.search(r'\[.*\]', text, re.DOTALL)
        if arr_match:
            try:
                updates = json.loads(arr_match.group())
            except json.JSONDecodeError:
                updates = []
        else:
            updates = []

    return updates, input_tokens, output_tokens


# --- Output ---

def print_report(news_items, updates, domain_filter, hours, positions_only):
    """Print formatted terminal report."""
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    domain_str = domain_filter or 'ALL'
    print(f"\n{'=' * 70}")
    print(f"NEWS CALIBRATOR — {now} — {domain_str} — Last {hours}h")
    print(f"{'=' * 70}")

    # News section
    matched = [n for n in news_items if n['relevance_score'] > 0]
    total = len(news_items)

    if positions_only:
        matched = [n for n in matched if n['matched_positions']]

    print(f"\n--- NEWS ({total} fetched, {len(matched)} matched) ---\n")

    if not matched:
        print("  No matched news items.\n")
    else:
        for i, item in enumerate(matched[:20]):
            cred = item.get('credibility_score')
            cred_str = f" ({cred:.1f}/5)" if cred else ""
            age = _format_age(item.get('published_dt'))
            print(f"  {i+1}. [{item['source']}]{cred_str} {age}")
            print(f"     {item['title']}")
            for mp in item.get('matched_positions', []):
                print(f"     -> {mp['trade_id']}: {mp['market']}")
            for mm in item.get('matched_markets', []):
                print(f"     -> {mm['title']}")
            print()

    # Calibration section
    if updates:
        print(f"--- CALIBRATION ({len(updates)} updates) ---\n")
        alerts = []
        for u in updates:
            market = u.get('market', 'Unknown')
            tid = u.get('trade_id', '')
            tid_str = f" ({tid})" if tid else ""
            prev = u.get('previous_estimate', '?')
            upd = u.get('updated_estimate', '?')
            delta = u.get('delta_pp', 0)
            conf = u.get('confidence', '?')
            reason = u.get('reasoning', '')

            delta_str = f"{delta:+d}pp" if isinstance(delta, (int, float)) else str(delta)
            print(f"  {market}{tid_str}")
            print(f"    Previous: {prev} | Updated: {upd} ({delta_str}) | {conf}")
            print(f"    {reason}")
            print()

            # Alert if significant
            if isinstance(delta, (int, float)) and abs(delta) >= 3:
                n_matched = sum(1 for n in matched
                                if any(mp.get('trade_id') == tid for mp in n.get('matched_positions', [])))
                alerts.append(f"  ! {tid or market}: {n_matched} matched items, estimate shifted {delta_str}")

        if alerts:
            print("--- ALERTS ---\n")
            for a in alerts:
                print(a)
            print()

    print(f"{'=' * 70}")


def output_json_report(news_items, updates, domain_filter, hours):
    """Output machine-readable JSON."""
    matched = [n for n in news_items if n['relevance_score'] > 0]
    # Clean up non-serializable fields
    for item in matched:
        item.pop('published_dt', None)

    output = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'domain': domain_filter or 'ALL',
        'hours': hours,
        'news_total': len(news_items),
        'news_matched': len(matched),
        'matched_items': matched[:25],
        'calibration_updates': updates or [],
    }
    print(json.dumps(output, indent=2, default=str))


def log_run(news_items, updates, model, input_tokens, output_tokens, domain_filter, hours):
    """Append run to JSONL log."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    matched = [n for n in news_items if n['relevance_score'] > 0]
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'domain': domain_filter or 'ALL',
        'hours': hours,
        'model': model,
        'news_fetched': len(news_items),
        'news_matched': len(matched),
        'updates': updates or [],
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
    }
    with open(LOG_FILE, 'a') as f:
        f.write(json.dumps(entry, default=str) + '\n')


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description='News Calibrator — RSS news to probability updates')
    parser.add_argument('--domain', type=str, default=None,
                        help='Filter by domain (GEO, POL, ECO, CRY, TEC, LAW, ENV, FIN, SCI, SOC)')
    parser.add_argument('--hours', type=int, default=12,
                        help='Lookback window in hours (default: 12)')
    parser.add_argument('--positions-only', action='store_true',
                        help='Only show news matching held positions')
    parser.add_argument('--no-ai', action='store_true',
                        help='Just show news feed, skip Claude calibration')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show Claude prompt without calling API')
    parser.add_argument('--json', action='store_true',
                        help='Machine-readable JSON output')
    parser.add_argument('--model', type=str, default=DEFAULT_MODEL,
                        help=f'Claude model to use (default: {DEFAULT_MODEL})')
    parser.add_argument('--max-news', type=int, default=25,
                        help='Max news items to send to Claude (default: 25)')
    parser.add_argument('--no-dedup', action='store_true',
                        help='Skip deduplication of seen items')
    args = parser.parse_args()

    if args.domain:
        args.domain = args.domain.upper()
        if args.domain not in FEEDS:
            print(f"Unknown domain: {args.domain}")
            print(f"Available: {', '.join(sorted(FEEDS.keys()))}")
            sys.exit(1)

    verbose = not args.json and not args.dry_run

    # Load credibility matrix
    cred_matrix = load_credibility_matrix()

    # Load dedup state
    seen = load_seen(args.no_dedup)

    # Fetch news
    domains = [args.domain] if args.domain else list(FEEDS.keys())
    all_news = []

    for domain in domains:
        if verbose:
            print(f"Fetching {domain} news...")
        items = fetch_domain_news(domain, args.hours, verbose=verbose)
        for item in items:
            item['domain'] = domain
        all_news.extend(items)

    if verbose:
        print(f"\nTotal raw items: {len(all_news)}")

    # Dedup
    new_items = []
    for item in all_news:
        h = news_hash(item['source'], item['title'])
        if h not in seen:
            seen[h] = datetime.now(timezone.utc).isoformat()
            new_items.append(item)

    if verbose and not args.no_dedup:
        print(f"After dedup: {len(new_items)} new items (filtered {len(all_news) - len(new_items)} seen)")

    if not args.no_dedup:
        save_seen(seen)

    # Attach credibility scores
    for item in new_items:
        score, _key = get_credibility_score(item['source'], cred_matrix)
        item['credibility_score'] = score

    # Load positions and active markets
    positions = load_positions()
    active_markets = []
    for domain in domains:
        active_markets.extend(parse_active_md(domain))

    if verbose:
        print(f"Loaded {len(positions)} positions, {len(active_markets)} tracked markets")

    # Match news to markets
    new_items = match_news_to_markets(new_items, positions, active_markets)

    # Sort by relevance
    new_items.sort(key=lambda x: x['relevance_score'], reverse=True)

    # AI calibration
    updates = None
    input_tokens = 0
    output_tokens = 0

    if not args.no_ai:
        prompt = build_calibration_prompt(new_items, positions, active_markets, args.domain)

        if args.dry_run:
            print("\n--- CLAUDE PROMPT (dry run) ---\n")
            print(prompt)
            print(f"\n--- END PROMPT ({len(prompt)} chars, ~{len(prompt)//4} tokens est.) ---")
            return

        matched_count = sum(1 for n in new_items if n['relevance_score'] > 0)
        if matched_count == 0:
            if verbose:
                print("\nNo matched news items — skipping Claude call.")
        else:
            if verbose:
                print(f"\nCalling Claude ({args.model})...")
            updates, input_tokens, output_tokens = call_claude(prompt, args.model)
            if verbose and updates is not None:
                print(f"  {len(updates)} updates | {input_tokens} in / {output_tokens} out tokens")

    # Output
    if args.json:
        output_json_report(new_items, updates, args.domain, args.hours)
    else:
        print_report(new_items, updates, args.domain, args.hours, args.positions_only)

    # Log
    if updates is not None:
        log_run(new_items, updates, args.model, input_tokens, output_tokens, args.domain, args.hours)


if __name__ == '__main__':
    main()

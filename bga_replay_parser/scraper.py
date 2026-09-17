"""
Selenium-based scraper for BoardGameArena replay pages (game-agnostic)
"""
import time
import os
import logging
import re
import requests
from typing import List, Optional, Dict
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from datetime import datetime
from .bga_session import BGASession

logger = logging.getLogger(__name__)

import config
from . import constants

class BGAScraper:
    """Scrapes BGA replays: login, gamereview version lookup, replay page / archive-log JSON."""
    
    def __init__(self, chromedriver_path: str, chrome_path: str=None, request_delay: int = 1, headless: bool = False,
                 email: Optional[str] = None, password: Optional[str] = None):
        """
        Initialize the scraper
        
        Args:
            chromedriver_path: Path to ChromeDriver executable
            request_delay: Delay between requests in seconds
            headless: Whether to run Chrome in headless mode
            email: BGA account email (optional, will try to load from config if not provided)
            password: BGA account password (optional, will try to load from config if not provided)
        """
        self.chromedriver_path = chromedriver_path
        self.chrome_path = chrome_path
        self.request_delay = request_delay
        self.headless = headless
        self.driver = None
        
        # Authentication credentials
        self.email = email
        self.password = password
        
        # Debug artifacts control - disabled by default for end users
        self.debug_artifacts_enabled = bool(os.environ.get("BGA_DEBUG", ""))
        
        # Try to load credentials from config if not provided
        if not self.email or not self.password:
            try:
                from config import BGA_EMAIL, BGA_PASSWORD
                self.email = self.email or BGA_EMAIL
                self.password = self.password or BGA_PASSWORD
            except ImportError:
                logger.warning("No credentials provided and could not load from config")
        
        # Session manager
        self.session: Optional[BGASession] = None
        
        # Session for direct HTTP requests
        self.requests_session: Optional[requests.Session] = None
        
        # Load speed settings: config.SPEED_PROFILE picks a profile from constants.SPEED_PROFILES
        self.speed_profile = getattr(config, "SPEED_PROFILE", "NORMAL")
        self.speed_settings = constants.SPEED_PROFILES[self.speed_profile]
        logger.info(f"Using speed profile: {self.speed_profile} -> {self.speed_settings}")
    
    def _debug_enabled(self) -> bool:
        """Check if debug artifacts should be enabled"""
        return (self.debug_artifacts_enabled or 
                bool(os.environ.get("BGA_DEBUG", "")) or 
                bool(os.environ.get("BGA_DEBUG_ALWAYS", "")))
    
    def start_browser_and_login(self) -> bool:
        """
        Start browser and perform automated login using session manager
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.email or not self.password:
            logger.error("Email and password are required for automated login")
            print("❌ Email and password are required for automated login")
            print("Please provide credentials via constructor or config.py")
            return False
        
        try:
            # Initialize session manager
            print("🔐 Starting automated login process...")
            self.session = BGASession(
                email=self.email,
                password=self.password,
                chromedriver_path=self.chromedriver_path,
                chrome_path=self.chrome_path,
                headless=self.headless
            )
            
            # Perform authentication
            if not self.session.login():
                logger.error("Authentication failed")
                print("❌ Automated login failed")
                return False
            
            # Get the authenticated browser driver
            self.driver = self.session.get_driver()
            
            print("✅ Automated login completed successfully!")
            return True
            
        except Exception as e:
            logger.error(f"Error during automated login: {e}")
            print(f"❌ Error during automated login: {e}")
            return False

    def start_browser(self):
        """Start the Chrome browser (legacy method - use start_browser_and_login for automated login)"""
        print("Starting Chrome browser...")
        
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument('--headless')
        
        # Add useful Chrome options
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')

        if self.chrome_path:
            # If a custom Chrome path is provided, set it
            chrome_options.binary_location = self.chrome_path

        # Set user agent to avoid detection
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        service = Service(self.chromedriver_path)
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        
        print("✅ Chrome browser started successfully!")
        return self.driver
    
    def login_to_bga(self):
        """Navigate to BGA and wait for user to log in manually"""
        if not self.driver:
            raise RuntimeError("Browser not started. Call start_browser() first.")
        
        print("Navigating to BoardGameArena...")
        self.driver.get("https://boardgamearena.com")
        
        print("\n" + "="*60)
        print("🔐 MANUAL LOGIN REQUIRED")
        print("Please log into BoardGameArena in the browser window that opened.")
        print("After logging in, come back here and press Enter to continue...")
        print("="*60)
        
        input("Press Enter when you're logged in and ready to continue...")
        
        # Verify login by checking for logout link or user menu
        try:
            # Look for common elements that indicate login
            WebDriverWait(self.driver, 10).until(
                lambda driver: 'logout' in driver.page_source.lower() or 
                              'my account' in driver.page_source.lower() or
                              'player_name' in driver.page_source.lower()
            )
            print("✅ Login verified!")
            return True
        except:
            print("⚠️  Could not verify login, but continuing anyway...")
            return True
    
    def _normalize_url_to_effective_origin(self, url: str) -> str:
        """
        Replace the scheme/host of a URL with the authenticated effective_base_origin (if any).
        Ensures we hit the same host we authenticated against (e.g., en.boardgamearena.com).
        """
        try:
            if self.session and getattr(self.session, 'effective_base_origin', None):
                from urllib.parse import urlparse, urlunparse
                target = urlparse(url)
                base = urlparse(self.session.effective_base_origin)
                if base.scheme and base.netloc and (target.netloc != base.netloc):
                    return urlunparse((base.scheme, base.netloc, target.path, target.params, target.query, target.fragment))
        except Exception:
            pass
        return url

    def _find_replay_content_in_frames(self, max_ms: int = 2500) -> bool:
        """
        Scan the top document and all iframes quickly for replay content indicators.
        If found, stores the detected frame's HTML in self._last_replay_source_html.
        Returns True if any context (top or frame) shows replay logs or g_gamelogs.
        """
        try:
            import time as _t
            start = _t.time()

            def _time_left() -> bool:
                return (_t.time() - start) * 1000.0 < max_ms

            def _check_current_context() -> bool:
                try:
                    result = self.driver.execute_script("""
                        try {
                            if (typeof g_gamelogs !== 'undefined' && g_gamelogs && g_gamelogs.length > 0) {
                                return 1;
                            }
                            if (document.querySelector('#replaylogs, #replaylogs_container, .replaylogs, .replay_logs')) {
                                return 1;
                            }
                            if (document.body && (document.body.innerHTML.includes('replaylogs_move') || document.body.innerHTML.includes('g_gamelogs'))) {
                                return 1;
                            }
                            return 0;
                        } catch (e) {
                            return 0;
                        }
                    """)
                    return bool(result)
                except Exception:
                    return False

            # Reset last captured source
            try:
                setattr(self, "_last_replay_source_html", None)
            except Exception:
                pass

            # Check top-level first
            if _check_current_context():
                try:
                    setattr(self, "_last_replay_source_html", self.driver.page_source)
                except Exception:
                    pass
                return True

            # Enumerate iframes and check each quickly
            try:
                frames = self.driver.find_elements(By.TAG_NAME, "iframe")
            except Exception:
                frames = []

            for frame in frames:
                if not _time_left():
                    break
                try:
                    self.driver.switch_to.frame(frame)
                    if _check_current_context():
                        try:
                            setattr(self, "_last_replay_source_html", self.driver.page_source)
                        except Exception:
                            pass
                        self.driver.switch_to.default_content()
                        return True
                except Exception:
                    # ignore and continue
                    try:
                        self.driver.switch_to.default_content()
                    except Exception:
                        pass
                    continue
                finally:
                    try:
                        self.driver.switch_to.default_content()
                    except Exception:
                        pass

            # Ensure we are back to default content
            try:
                self.driver.switch_to.default_content()
            except Exception:
                pass
            return False
        except Exception:
            try:
                self.driver.switch_to.default_content()
            except Exception:
                pass
            return False

    def _replay_debug_init(self):
        """Initialize replay debug event buffer."""
        try:
            self._replay_debug_events = []
        except Exception:
            pass

    def _replay_debug_log(self, msg: str):
        """Append a small debug message for replay diagnostics."""
        try:
            if not hasattr(self, "_replay_debug_events"):
                self._replay_debug_events = []
            self._replay_debug_events.append(str(msg))
        except Exception:
            pass

    def _debug_ensure_dir(self, dir_path: str):
        """Ensure a directory exists."""
        try:
            os.makedirs(dir_path, exist_ok=True)
        except Exception:
            pass

    def _collect_iframe_srcs_quick(self, base_html: Optional[str] = None) -> List[str]:
        """Collect iframe srcs from DOM (JS) or fallback parse HTML."""
        srcs: List[str] = []
        try:
            srcs = self.driver.execute_script("""
                try {
                    return Array.from(document.querySelectorAll('iframe'))
                        .map(f => f.getAttribute('src'))
                        .filter(s => !!s);
                } catch (e) { return []; }
            """) or []
        except Exception:
            srcs = []
        if not srcs and base_html:
            try:
                soup_ifr = BeautifulSoup(base_html, 'html.parser')
                srcs = [ifr.get('src') for ifr in soup_ifr.find_all('iframe') if ifr.get('src')]
            except Exception:
                pass
        return srcs

    def _dump_replay_debug_artifacts(self, table_id: str, nav_url: str, meta: Dict[str, str], page_source: str):
        """
        Write debug artifacts to ./debug for replay diagnostics:
        - meta txt (urls, readyState, cookies, iframe list, events)
        - top html snapshot
        - up to 3 iframe html snapshots
        - performance entries json
        """
        # Skip debug artifact creation unless explicitly enabled
        if not (self._debug_enabled() or os.environ.get("BGA_DEBUG_ALWAYS")):
            return
        
        try:
            import json
            debug_dir = os.path.abspath(os.path.join(os.getcwd(), "debug"))
            self._debug_ensure_dir(debug_dir)

            # Meta file
            meta_path = os.path.join(debug_dir, f"replay_debug_meta_{table_id}.txt")
            try:
                with open(meta_path, "w", encoding="utf-8") as f:
                    f.write(f"nav_url: {nav_url}\n")
                    for k, v in meta.items():
                        try:
                            f.write(f"{k}: {v}\n")
                        except Exception:
                            pass
                    # Replay debug events
                    f.write("\n-- replay_debug_events --\n")
                    events = getattr(self, "_replay_debug_events", [])
                    for e in (events or []):
                        try:
                            f.write(f"{e}\n")
                        except Exception:
                            pass
            except Exception:
                pass

            # Top HTML snapshot
            top_path = os.path.join(debug_dir, f"replay_debug_top_{table_id}.html")
            try:
                with open(top_path, "w", encoding="utf-8") as f:
                    f.write(page_source or "")
            except Exception:
                pass

            # Iframe HTML snapshots (up to first 3)
            try:
                frames = self.driver.find_elements(By.TAG_NAME, "iframe")
            except Exception:
                frames = []
            iframe_paths = []
            idx = 0
            for frame in frames[:3]:
                try:
                    self.driver.switch_to.frame(frame)
                    iframe_html = self.driver.page_source
                except Exception:
                    iframe_html = ""
                finally:
                    try:
                        self.driver.switch_to.default_content()
                    except Exception:
                        pass
                try:
                    iframe_path = os.path.join(debug_dir, f"replay_debug_iframe_{idx}_{table_id}.html")
                    with open(iframe_path, "w", encoding="utf-8") as f:
                        f.write(iframe_html or "")
                    try:
                        iframe_paths.append(iframe_path)
                    except Exception:
                        pass
                except Exception:
                    pass
                idx += 1

            # performance entries
            perf_entries = []
            try:
                perf_entries = self.driver.execute_script("""
                    try { return (performance.getEntries() || []).map(e => e.name).slice(0, 200); }
                    catch (e) { return []; }
                """) or []
            except Exception:
                pass
            try:
                perf_path = os.path.join(debug_dir, f"replay_debug_perf_{table_id}.json")
                with open(perf_path, "w", encoding="utf-8") as f:
                    json.dump(perf_entries, f, ensure_ascii=False, indent=2)
                # Record last debug artifacts for GUI/diagnostics and print absolute paths
                try:
                    abs_meta = os.path.abspath(meta_path)
                    abs_top = os.path.abspath(top_path)
                    abs_perf = os.path.abspath(perf_path)
                    abs_iframes = [os.path.abspath(p) for p in (iframe_paths or [])]
                    self._last_debug_artifacts = {
                        "table_id": table_id,
                        "nav_url": nav_url,
                        "meta": abs_meta,
                        "top": abs_top,
                        "iframes": abs_iframes,
                        "perf": abs_perf
                    }
                    try:
                        print(f"🔍 Debug artifacts saved: meta={abs_meta}, top={abs_top}, perf={abs_perf}, iframes_count={len(abs_iframes)}")
                    except Exception:
                        pass
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            # Swallow debug write errors
            pass

    def extract_version_from_gamereview(self, table_id: str) -> Optional[str]:
        """
        Extract the version number from the gamereview page using multiple robust patterns
        
        Args:
            table_id: BGA table ID
            
        Returns:
            str: Version number (e.g., "250505-1448") or None if not found
        """
        if not self.driver:
            raise RuntimeError("Browser not started. Call start_browser() first.")
        
        gamereview_url = f"https://boardgamearena.com/gamereview?table={table_id}"
        logger.info(f"Extracting version from gamereview page: {gamereview_url}")
        
        try:
            # Navigate to the gamereview page
            print(f"Navigating to gamereview page: {gamereview_url}")
            normalized_url = self._normalize_url_to_effective_origin(gamereview_url)
            self.driver.get(normalized_url)
            
            # Wait for JavaScript content to load instead of just using a fixed delay
            if not self._wait_for_gamereview_content_to_load(table_id):
                print("❌ Gamereview content failed to load properly")
                return None
            
            # Get the page source after content has loaded
            page_source = self.driver.page_source
            
            # Log basic page characteristics for debugging
            logger.info(f"Content loaded successfully - HTML length: {len(page_source)} chars")
            
            # Try multiple extraction patterns in order of reliability
            version = self._extract_version_with_multiple_patterns(page_source, table_id)
            
            if version:
                logger.info(f"Successfully extracted version: {version}")
                print(f"✅ Found version number: {version}")
                return version
            else:
                logger.warning(f"No version number found in gamereview page for table {table_id}")
                print("⚠️  No version number found in gamereview page")
                
                # Save HTML and debug info when extraction fails
                self._save_debug_info_for_failed_extraction(table_id, page_source, gamereview_url)
                return None
            
        except Exception as e:
            logger.error(f"Error extracting version from gamereview for {table_id}: {e}")
            print(f"❌ Error extracting version: {e}")
            return None

    def _extract_version_with_multiple_patterns(self, html_content: str, table_id: str) -> Optional[str]:
        """
        Extract version number using only the most reliable pattern (replay URLs)
        
        Args:
            html_content: HTML content of the gamereview page
            table_id: Table ID for logging purposes
            
        Returns:
            str: Version number if found, None otherwise
        """
        logger.debug(f"Extracting version from replay URLs for table {table_id}")
        
        # Use only the most reliable pattern: Direct replay links
        # This pattern has proven to be the most accurate in testing
        replay_pattern = r'/archive/replay/(\d{6}-\d{4})/'
        
        try:
            matches = re.findall(replay_pattern, html_content, re.IGNORECASE)
            logger.info(f"Replay URL pattern search: found {len(matches)} matches")
            
            if matches:
                # Remove duplicates and get the first unique match
                unique_matches = list(dict.fromkeys(matches))  # Preserves order
                version = unique_matches[0]
                
                logger.info(f"Version found using replay URL pattern: {version}")
                logger.debug(f"Replay URL pattern found {len(matches)} total matches, using first unique: {version}")
                
                # Validate the version format (6 digits, dash, 4 digits)
                if re.match(r'^\d{6}-\d{4}$', version):
                    return version
                else:
                    logger.warning(f"Invalid version format from replay URL: {version}")
                    return None
            else:
                # Log some context about what we're searching in
                logger.info(f"No replay URL matches found. HTML contains 'archive': {'archive' in html_content.lower()}")
                logger.info(f"HTML contains 'replay': {'replay' in html_content.lower()}")
                
                # Look for any archive/replay patterns for debugging
                archive_patterns = re.findall(r'/archive/[^/]+/[^/\s"\'<>]+', html_content, re.IGNORECASE)
                if archive_patterns:
                    logger.info(f"Found {len(archive_patterns)} archive patterns (not matching version format): {archive_patterns[:5]}")
                else:
                    logger.info("No archive patterns found at all")
                    
        except Exception as e:
            logger.error(f"Error with replay URL pattern: {e}")
        
        logger.debug(f"No version number found in replay URLs for table {table_id}")
        return None

    def _save_debug_info_for_failed_extraction(self, table_id: str, html_content: str, gamereview_url: str):
        """
        Save HTML content and debug information when version extraction fails
        
        Args:
            table_id: BGA table ID
            html_content: HTML content of the gamereview page
            gamereview_url: URL of the gamereview page
        """
        # Skip debug artifact creation unless explicitly enabled
        if not self._debug_enabled():
            return
        
        try:
            import json
            
            # Create timestamp for unique filenames
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Save HTML content
            html_filename = f"gamereview_{table_id}_{timestamp}.html"
            with open(html_filename, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            # Create debug information
            debug_info = {
                'table_id': table_id,
                'timestamp': timestamp,
                'gamereview_url': gamereview_url,
                'html_filename': html_filename,
                'page_characteristics': self._analyze_page_characteristics(html_content),
                'pattern_analysis': self._analyze_version_patterns(html_content),
                'extraction_context': {
                    'speed_profile': self.speed_profile,
                    'speed_settings': self.speed_settings,
                    'headless_mode': self.headless
                }
            }
            
            # Save debug JSON
            json_filename = f"version_debug_results_{table_id}_{timestamp}.json"
            with open(json_filename, 'w', encoding='utf-8') as f:
                json.dump(debug_info, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Debug info saved: {html_filename} and {json_filename}")
            print(f"🔍 Debug files saved: {html_filename} and {json_filename}")
            
        except Exception as e:
            logger.error(f"Error saving debug info: {e}")
            print(f"❌ Error saving debug info: {e}")

    def _analyze_page_characteristics(self, html_content: str) -> Dict:
        """
        Analyze basic characteristics of the HTML page
        
        Args:
            html_content: HTML content to analyze
            
        Returns:
            dict: Analysis results
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract title
            title = soup.find('title')
            title_text = title.get_text().strip() if title else "No title found"
            
            # Check for key elements
            characteristics = {
                'title': title_text,
                'has_archive_links': 'archive' in html_content.lower(),
                'has_replay_links': 'replay' in html_content.lower(),
                'has_table_references': f'table' in html_content.lower(),
                'has_version_patterns': bool(re.search(r'\d{6}-\d{4}', html_content)),
                'script_tags_count': len(soup.find_all('script')),
                'div_count': len(soup.find_all('div')),
                'link_count': len(soup.find_all('a')),
                'contains_error_messages': any(error in html_content.lower() for error in ['error', 'fatal', 'must be logged']),
                'page_seems_loaded': len(html_content) > 10000  # Rough heuristic
            }
            
            return characteristics
            
        except Exception as e:
            logger.error(f"Error analyzing page characteristics: {e}")
            return {'error': str(e)}

    def _analyze_version_patterns(self, html_content: str) -> Dict:
        """
        Analyze version-related patterns in the HTML content
        
        Args:
            html_content: HTML content to analyze
            
        Returns:
            dict: Pattern analysis results
        """
        try:
            analysis = {}
            
            # Primary pattern: replay URLs
            replay_pattern = r'/archive/replay/(\d{6}-\d{4})/'
            replay_matches = re.findall(replay_pattern, html_content, re.IGNORECASE)
            analysis['replay_url_pattern'] = {
                'pattern': replay_pattern,
                'matches_count': len(replay_matches),
                'matches': replay_matches[:10],  # First 10 matches
                'unique_matches': list(dict.fromkeys(replay_matches))[:10]
            }
            
            # Look for any 6-4 digit patterns
            version_pattern = r'\b(\d{6}-\d{4})\b'
            version_matches = re.findall(version_pattern, html_content)
            analysis['general_version_pattern'] = {
                'pattern': version_pattern,
                'matches_count': len(version_matches),
                'matches': version_matches[:10],
                'unique_matches': list(dict.fromkeys(version_matches))[:10]
            }
            
            # Look for archive patterns (broader)
            archive_pattern = r'/archive/[^/\s"\'<>]+'
            archive_matches = re.findall(archive_pattern, html_content, re.IGNORECASE)
            analysis['archive_pattern'] = {
                'pattern': archive_pattern,
                'matches_count': len(archive_matches),
                'matches': archive_matches[:10],
                'unique_matches': list(dict.fromkeys(archive_matches))[:10]
            }
            
            # Sample content around potential matches
            if replay_matches:
                # Find context around the first replay match
                first_match = replay_matches[0]
                match_index = html_content.find(f'/archive/replay/{first_match}/')
                if match_index != -1:
                    start = max(0, match_index - 200)
                    end = min(len(html_content), match_index + 200)
                    analysis['first_match_context'] = html_content[start:end]
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing version patterns: {e}")
            return {'error': str(e)}

    def _wait_for_gamereview_content_to_load(self, table_id: str) -> bool:
        """
        Wait for the gamereview page JavaScript content to load properly
        
        Args:
            table_id: BGA table ID for logging purposes
            
        Returns:
            bool: True if content loaded successfully, False if timeout or error
        """
        try:
            timeout = self.speed_settings.get('element_wait_timeout', 10)

            print(f"⏱️  Waiting for JavaScript content to load (timeout: {timeout}s)")
            logger.info(f"Waiting for gamereview content to load for table {table_id}")
            
            # Strategy 1: Wait for specific content indicators to appear
            wait = WebDriverWait(self.driver, timeout)

            # Quick frame-aware scan before longer strategies (fits within ~3s cap)
            try:
                max_ms = max(500, int(timeout * 1000) - 200)
                if self._find_replay_content_in_frames(max_ms=max_ms):
                    logger.info("Replay content detected in frame or top context (fast scan)")
                    return True
            except Exception:
                pass
            
            # Try multiple strategies to detect when content is loaded
            content_loaded = False
            
            # Strategy 1: Wait for replay links to appear
            try:
                logger.info("Strategy 1: Waiting for replay links to appear...")
                wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(@href, '/archive/replay/')]")))
                logger.info("Replay links found - content appears to be loaded")
                print("✅ Replay links detected - content loaded")
                content_loaded = True
            except:
                logger.info("Strategy 1 failed: No replay links found")
            
            # Strategy 2: Wait for player selection elements (common in gamereview pages)
            if not content_loaded:
                try:
                    logger.info("Strategy 2: Waiting for player selection elements...")
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.playerselection, div.score-entry")))
                    logger.info("Player selection elements found")
                    print("✅ Player selection elements detected - content loaded")
                    content_loaded = True
                except:
                    logger.info("Strategy 2 failed: No player selection elements found")
            
            # Strategy 3: Wait for overall-content div to be populated
            if not content_loaded:
                try:
                    logger.info("Strategy 3: Waiting for overall-content to be populated...")
                    
                    def content_populated(driver):
                        try:
                            overall_content = driver.find_element(By.ID, "overall-content")
                            # Check if it has meaningful content (not just empty or minimal)
                            content_text = overall_content.text.strip()
                            inner_html = overall_content.get_attribute('innerHTML').strip()
                            
                            # Content is considered loaded if:
                            # 1. It has substantial text content, OR
                            # 2. It has substantial HTML content with meaningful elements
                            has_text = len(content_text) > 100
                            has_html = len(inner_html) > 1000 and ('playerselection' in inner_html or 'archive/replay' in inner_html)
                            
                            if has_text or has_html:
                                logger.info(f"Overall-content populated: text={len(content_text)} chars, html={len(inner_html)} chars")
                                return True
                            return False
                        except:
                            return False
                    
                    wait.until(content_populated)
                    logger.info("Overall-content div populated with meaningful content")
                    print("✅ Page content populated - content loaded")
                    content_loaded = True
                except:
                    logger.info("Strategy 3 failed: Overall-content not populated")
            
            # Strategy 4: Progressive delay with content checks
            if not content_loaded:
                logger.info("Strategy 4: Using progressive delays with content validation...")
                delays = [1.0, 2.0, 3.0, 5.0]  # Progressive delays
                
                for delay in delays:
                    print(f"⏱️  Waiting {delay}s for content to load...")
                    time.sleep(delay)
                    
                    # Check if content has appeared
                    page_source = self.driver.page_source
                    
                    # Look for replay URLs in the page source
                    if '/archive/replay/' in page_source and re.search(r'/archive/replay/\d{6}-\d{4}/', page_source):
                        logger.info(f"Content loaded after {delay}s delay - replay URLs found")
                        print(f"✅ Content loaded after {delay}s - replay URLs detected")
                        content_loaded = True
                        break
                    
                    # Look for substantial content in overall-content div
                    try:
                        soup = BeautifulSoup(page_source, 'html.parser')
                        overall_content = soup.find('div', id='overall-content')
                        if overall_content:
                            content_text = overall_content.get_text().strip()
                            if len(content_text) > 100:
                                logger.info(f"Content loaded after {delay}s delay - substantial text found")
                                print(f"✅ Content loaded after {delay}s - page content detected")
                                content_loaded = True
                                break
                    except:
                        pass
                    
                    logger.info(f"Content not ready after {delay}s, trying next delay...")
            
            if content_loaded:
                # Give a small additional delay to ensure everything is fully rendered
                time.sleep(0.5)
                logger.info("Content loading completed successfully")
                return True
            else:
                logger.warning(f"Content failed to load within timeout for table {table_id}")
                print("⚠️  Content loading timeout - proceeding anyway")
                
                # Even if we timeout, let's try to proceed - sometimes content is there but not detected
                return True
                
        except Exception as e:
            logger.error(f"Error waiting for content to load: {e}")
            print(f"❌ Error waiting for content: {e}")
            # Don't fail completely - try to proceed
            return True

    def _wait_for_replay_content_to_load(self, replay_id: str) -> bool:
        """
        Wait for the replay page content to load properly, specifically focusing on g_gamelogs
        
        Args:
            replay_id: BGA replay ID for logging purposes
            
        Returns:
            bool: True if content loaded successfully, False if timeout or error
        """
        try:
            timeout = self.speed_settings.get('element_wait_timeout', 10)

            print(f"⏱️  Waiting for replay content to load (timeout: {timeout}s)")
            logger.info(f"Waiting for replay content to load for replay {replay_id}")
            
            # Strategy 1: Wait for specific content indicators to appear
            wait = WebDriverWait(self.driver, timeout)

            # Quick frame-aware scan before longer strategies (fits within ~3s cap)
            try:
                max_ms = max(500, int(timeout * 1000) - 200)
                if self._find_replay_content_in_frames(max_ms=max_ms):
                    logger.info("Replay content detected in frame or top context (fast scan)")
                    return True
            except Exception:
                pass
            
            # Try multiple strategies to detect when content is loaded
            content_loaded = False
            
            # Strategy 1: Wait for g_gamelogs JavaScript variable to be populated
            try:
                logger.info("Strategy 1: Waiting for g_gamelogs JavaScript variable...")
                
                def gamelogs_populated(driver):
                    try:
                        # Execute JavaScript to check if g_gamelogs exists and has content
                        result = driver.execute_script("""
                            try {
                                if (typeof g_gamelogs !== 'undefined' && g_gamelogs && g_gamelogs.length > 0) {
                                    return g_gamelogs.length;
                                }
                                if (document.querySelector('#replaylogs, #replaylogs_container, .replaylogs, .replay_logs')) {
                                    return 1;
                                }
                                if (document.body && (document.body.innerHTML.includes('replaylogs_move') || document.body.innerHTML.includes('g_gamelogs'))) {
                                    return 1;
                                }
                                return 0;
                            } catch (e) {
                                return 0;
                            }
                        """)
                        
                        if result and result > 0:
                            logger.info(f"Found g_gamelogs with {result} entries")
                            return True
                        return False
                    except Exception as e:
                        logger.debug(f"Error checking g_gamelogs: {e}")
                        return False
                
                wait.until(gamelogs_populated)
                logger.info("g_gamelogs JavaScript variable populated - content appears to be loaded")
                print("✅ g_gamelogs detected - content loaded")
                content_loaded = True
            except:
                logger.info("Strategy 1 failed: g_gamelogs not found or not populated")
            
            # Strategy 2: Wait for replay log DOM elements to appear
            if not content_loaded:
                try:
                    logger.info("Strategy 2: Waiting for replay log elements...")
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.replaylogs_move")))
                    
                    # Verify we have multiple log entries (typical replay has many moves)
                    log_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.replaylogs_move")
                    if len(log_elements) >= 1:  # At least one move
                        logger.info(f"Found {len(log_elements)} replay log elements - content appears loaded")
                        print(f"✅ Replay logs detected ({len(log_elements)} moves) - content loaded")
                        content_loaded = True
                    else:
                        logger.info(f"Only found {len(log_elements)} replay log elements - waiting for more")
                except:
                    logger.info("Strategy 2 failed: No replay log elements found")
            
            # Strategy 3: Wait for player selection or game interface elements
            if not content_loaded:
                try:
                    logger.info("Strategy 3: Waiting for player selection elements...")
                    wait.until(EC.any_of(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.playerselection")),
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.player_board")),
                        EC.presence_of_element_located((By.CSS_SELECTOR, "span.playername"))
                    ))
                    logger.info("Player interface elements found")
                    print("✅ Player interface detected - content loaded")
                    content_loaded = True
                except:
                    logger.info("Strategy 3 failed: No player interface elements found")
            
            # Strategy 4: Wait for overall-content div to be populated with replay-specific content
            if not content_loaded:
                try:
                    logger.info("Strategy 4: Waiting for overall-content to be populated with replay content...")
                    
                    def replay_content_populated(driver):
                        try:
                            overall_content = driver.find_element(By.ID, "overall-content")
                            content_text = overall_content.text.strip()
                            inner_html = overall_content.get_attribute('innerHTML').strip()
                            
                            # Content is considered loaded if:
                            # 1. It has substantial text content, AND
                            # 2. It contains replay-specific indicators
                            has_text = len(content_text) > 200
                            has_replay_content = any(indicator in inner_html.lower() for indicator in [
                                'replaylogs', 'playername', 'playerselection', 'g_gamelogs'
                            ])
                            
                            if has_text and has_replay_content:
                                logger.info(f"Replay content populated: text={len(content_text)} chars, has_replay_content={has_replay_content}")
                                return True
                            return False
                        except:
                            return False
                    
                    wait.until(replay_content_populated)
                    logger.info("Overall-content div populated with replay content")
                    print("✅ Replay content populated - content loaded")
                    content_loaded = True
                except:
                    logger.info("Strategy 4 failed: Overall-content not populated with replay content")
            
            # Strategy 5: Progressive delay with content validation (fallback)
            if not content_loaded:
                logger.info("Strategy 5: Using progressive delays with content validation...")
                delays = [1.0, 2.0]  # Short delays for replay pages (max ~3s)
                
                for delay in delays:
                    print(f"⏱️  Waiting {delay}s for content to load...")
                    time.sleep(delay)
                    
                    # Check if content has appeared
                    page_source = self.driver.page_source
                    
                    # Look for g_gamelogs in the page source
                    if 'g_gamelogs' in page_source and 'replaylogs_move' in page_source:
                        logger.info(f"Content loaded after {delay}s delay - g_gamelogs and replay logs found")
                        print(f"✅ Content loaded after {delay}s - replay data detected")
                        content_loaded = True
                        break
                    
                    # Look for replay log elements
                    try:
                        soup = BeautifulSoup(page_source, 'html.parser')
                        replay_logs = soup.find_all('div', class_='replaylogs_move')
                        if len(replay_logs) >= 1:
                            logger.info(f"Content loaded after {delay}s delay - {len(replay_logs)} replay logs found")
                            print(f"✅ Content loaded after {delay}s - replay logs detected")
                            content_loaded = True
                            break
                    except:
                        pass
                    
                    # Check for substantial content with replay indicators
                    if any(indicator in page_source.lower() for indicator in [
                        'replaylogs', 'g_gamelogs', 'playerselection'
                    ]) and len(page_source) > 10000:
                        logger.info(f"Content loaded after {delay}s delay - replay indicators found")
                        print(f"✅ Content loaded after {delay}s - replay indicators detected")
                        content_loaded = True
                        break
                    
                    logger.info(f"Content not ready after {delay}s, trying next delay...")
            
            if content_loaded:
                # Give a small additional delay to ensure everything is fully rendered
                time.sleep(0.3)  # Short final delay for replay pages
                logger.info("Replay content loading completed successfully")
                return True
            else:
                logger.warning(f"Replay content failed to load within timeout for replay {replay_id}")
                print("⚠️  Replay content loading timeout - proceeding anyway")
                
                # Even if we timeout, let's try to proceed - sometimes content is there but not detected
                return True
                
        except Exception as e:
            logger.error(f"Error waiting for replay content to load: {e}")
            print(f"❌ Error waiting for replay content: {e}")
            # Don't fail completely - try to proceed
            return True

    def scrape_replay(self, url: str, save_raw: bool = True, raw_data_dir: str = None, player_perspective: str = None) -> Optional[Dict]:
        """
        Scrape a single replay page
        
        Args:
            url: BGA replay URL
            save_raw: Whether to save raw HTML
            raw_data_dir: Directory to save raw HTML files
            player_perspective: Optional player perspective for file organization (overrides URL extraction)
            
        Returns:
            dict: Scraped data or None if failed
        """
        # Handle memory-only mode
        if raw_data_dir is None and hasattr(config, 'RAW_DATA_DIR'):
            raw_data_dir = constants.RAW_DATA_DIR
            
        if not self.driver:
            raise RuntimeError("Browser not started. Call start_browser() first.")
        
        # Extract replay ID from URL
        replay_id = self._extract_replay_id(url)
        if not replay_id:
            logger.error(f"Could not extract replay ID from {url}")
            return None
        
        logger.info(f"Scraping replay {replay_id}")
        
        try:
            # Navigate to the replay URL
            print(f"Navigating to: {url}")
            nav_url = self._normalize_url_to_effective_origin(url)
            self.driver.get(nav_url)
            
            # Init debug (lightweight, no extra wait)
            self._replay_debug_init()
            try:
                self._replay_debug_log(f"navigated_to={nav_url}")
                rs = self.driver.execute_script("return document.readyState") or ""
                self._replay_debug_log(f"readyState={rs}")
                cur = self.driver.current_url
                self._replay_debug_log(f"current_url={cur}")
                ck = []
                try:
                    ck = [c.get('name') for c in self.driver.get_cookies()] or []
                except Exception:
                    ck = []
                self._replay_debug_log(f"cookie_count={len(ck)}; names_sample={ck[:5]}")
                ifr = self._collect_iframe_srcs_quick()
                self._replay_debug_log(f"iframe_srcs_count={len(ifr)}; first={ifr[0] if ifr else ''}")
            except Exception:
                pass
            # Optional forced snapshot of page after navigation (env-controlled)
            try:
                if os.environ.get("BGA_DEBUG_ALWAYS"):
                    meta = {
                        "current_url": self.driver.current_url,
                        "readyState": self.driver.execute_script("return document.readyState") or "",
                        "forced_dump": "1"
                    }
                    self._dump_replay_debug_artifacts(replay_id, nav_url, meta, self.driver.page_source or "")
            except Exception:
                pass

            # Immediate auth check to avoid waiting when redirected to login
            current_url = self.driver.current_url
            page_check = self.driver.page_source.lower()
            if (current_url.endswith('/account/account/login.html')
                or 'form_id="loginform"' in page_check
                or '/account/account/login.html' in page_check):
                if not self._handle_authentication_error_with_retry(url):
                    logger.error(f"Authentication failed permanently for {url}")
                    print(f"❌ Authentication failed permanently for replay {replay_id}")
                    try:
                        meta = {
                            "current_url": self.driver.current_url,
                            "readyState": self.driver.execute_script("return document.readyState") or "",
                            "auth_status": "login_detected_reauth_failed"
                        }
                        self._dump_replay_debug_artifacts(replay_id, nav_url, meta, self.driver.page_source or "")
                    except Exception:
                        pass
                    return None

            # Wait for replay content to load using smart detection (capped at ~3s)
            if not self._wait_for_replay_content_to_load(replay_id):
                print("❌ Replay content failed to load properly")
                # Continue anyway - sometimes content is there but not detected
            
            # Check if we got an error page
            page_source = getattr(self, "_last_replay_source_html", None) or self.driver.page_source
            
            # Check for replay limit reached
            if self._check_replay_limit_reached(page_source):
                logger.warning(f"Replay limit reached when accessing {url}")
                print("🚫 You have reached your daily replay limit!")
                print("   BGA has daily limits on replay access to prevent server overload.")
                print("   Please try again tomorrow or wait for the limit to reset.")
                return {
                    'replay_id': replay_id,
                    'url': url,
                    'scraped_at': datetime.now().isoformat(),
                    'error': 'replay_limit_reached',
                    'limit_reached': True
                }
            
            # Check for permanently deleted/lost replay
            if self._is_deleted_replay(page_source):
                logger.warning(f"Replay permanently deleted/lost: {url}")
                print("  Replay has been permanently lost (empty archive)")
                return {
                    'replay_id': replay_id, 'url': url,
                    'scraped_at': datetime.now().isoformat(),
                    'error': 'replay_deleted', 'replay_deleted': True
                }

            # Check for authentication errors with retry logic
            if self._is_authentication_error(page_source):
                if not self._handle_authentication_error_with_retry(url):
                    logger.error(f"Authentication failed permanently for {url}")
                    print(f"❌ Authentication failed permanently for replay {replay_id}")
                    try:
                        meta = {
                            "current_url": self.driver.current_url,
                            "readyState": self.driver.execute_script("return document.readyState") or "",
                            "auth_status": "auth_error_reauth_failed"
                        }
                        self._dump_replay_debug_artifacts(replay_id, nav_url, meta, self.driver.page_source or "")
                    except Exception:
                        pass
                    return None

                # After successful re-authentication, get the fresh page source
                page_source = self.driver.page_source

            if 'fatal error' in page_source.lower() and 'must be logged' not in page_source.lower():
                print("❌ Fatal error on page - replay might not be accessible")
                return None
            
            # Try fetching iframe src directly if present and logs not evident
            if ('replaylogs_move' not in page_source.lower()) and ('g_gamelogs' not in page_source.lower()):
                try:
                    iframe_srcs = []
                    try:
                        # Collect iframe src attributes via JS for speed
                        iframe_srcs = self.driver.execute_script("""
                            try {
                                return Array.from(document.querySelectorAll('iframe'))
                                    .map(f => f.getAttribute('src'))
                                    .filter(s => s && s.includes('/archive/replay/'));
                            } catch (e) { return []; }
                        """) or []
                    except Exception:
                        iframe_srcs = []
                    # Fallback: parse current HTML for iframe src if JS failed
                    if not iframe_srcs:
                        try:
                            soup_ifr = BeautifulSoup(page_source, 'html.parser')
                            iframe_srcs = [ifr.get('src') for ifr in soup_ifr.find_all('iframe') if ifr.get('src') and '/archive/replay/' in ifr.get('src')]
                        except Exception:
                            iframe_srcs = []
                    # Fetch the first replay iframe src via authenticated requests
                    if iframe_srcs:
                        if not self.requests_session:
                            self.initialize_session()
                        if self.requests_session:
                            from urllib.parse import urljoin
                            iframe_url = urljoin(nav_url, iframe_srcs[0])
                            resp_ifr = self.requests_session.get(iframe_url, timeout=10)
                            if resp_ifr.status_code == 200:
                                low = resp_ifr.text.lower()
                                if not self._check_replay_limit_reached(resp_ifr.text) and not self._is_authentication_error(resp_ifr.text):
                                    if ('replaylogs_move' in low) or ('g_gamelogs' in low):
                                        logger.info("Using iframe direct fetch for replay content")
                                        page_source = resp_ifr.text
                except Exception as e:
                    logger.debug(f"Iframe direct fetch failed: {e}")

            # Fallback: if replay logs not evident, try a quick direct HTTP fetch
            if ('replaylogs_move' not in page_source.lower()) and ('g_gamelogs' not in page_source.lower()):
                try:
                    if not self.requests_session:
                        self.initialize_session()
                    if self.requests_session:
                        resp = self.requests_session.get(nav_url, timeout=15)
                        if resp.status_code == 200:
                            resp_text_lower = resp.text.lower()
                            if not self._check_replay_limit_reached(resp.text) and not self._is_authentication_error(resp.text):
                                if ('replaylogs_move' in resp_text_lower) or ('g_gamelogs' in resp_text_lower):
                                    logger.info("Using direct HTTP fetch fallback for replay content")
                                    page_source = resp.text
                except Exception as e:
                    logger.debug(f"Direct fetch fallback failed: {e}")

            # If replay signals not found, dump debug artifacts (fast, no extra waiting)
            try:
                low_for_dump = page_source.lower() if page_source else ""
                if ('replaylogs_move' not in low_for_dump) and ('g_gamelogs' not in low_for_dump):
                    meta = {
                        "current_url": self.driver.current_url,
                        "readyState": self.driver.execute_script("return document.readyState") or "",
                        "auth_status": ("login_detected" if (('form_id=\"loginform\"' in low_for_dump) or ('/account/account/login.html' in low_for_dump)) else "ok"),
                        "iframe_count": str(len(self._collect_iframe_srcs_quick(low_for_dump))),
                        "has_last_frame_source": str(bool(getattr(self, "_last_replay_source_html", None))),
                    }
                    self._dump_replay_debug_artifacts(replay_id, nav_url, meta, page_source)
            except Exception:
                pass

            # Save raw HTML if requested and raw_data_dir is provided
            if save_raw and raw_data_dir:
                # Use provided player_perspective or extract from URL as fallback
                if not player_perspective:
                    from urllib.parse import urlparse, parse_qs
                    parsed_url = urlparse(url)
                    query_params = parse_qs(parsed_url.query)
                    player_perspective = query_params.get('player', [None])[0]
                
                if player_perspective:
                    # Create player perspective directory
                    player_raw_dir = os.path.join(raw_data_dir, player_perspective)
                    os.makedirs(player_raw_dir, exist_ok=True)
                    raw_file_path = os.path.join(player_raw_dir, f"replay_{replay_id}.html")
                else:
                    # Fallback to root directory if no player perspective found
                    os.makedirs(raw_data_dir, exist_ok=True)
                    raw_file_path = os.path.join(raw_data_dir, f"replay_{replay_id}.html")
                
                with open(raw_file_path, 'w', encoding='utf-8') as f:
                    f.write(page_source)
                logger.info(f"Saved raw HTML to {raw_file_path}")
            
            # Parse the HTML to extract basic information
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Extract basic replay information
            replay_data = {
                'replay_id': replay_id,
                'url': url,
                'scraped_at': datetime.now().isoformat(),
                'title': None,
                'players': [],
                'game_logs_found': False,
                'html_content': page_source  # Always include HTML content for memory-only mode
            }
            
            # Try to extract title
            title_elem = soup.find('title')
            if title_elem:
                replay_data['title'] = title_elem.get_text().strip()

            # Look for game logs section
            game_logs = soup.find_all('div', class_='replaylogs_move')
            if game_logs:
                replay_data['game_logs_found'] = True
                replay_data['num_moves'] = len(game_logs)
                logger.info(f"Found {len(game_logs)} game log entries")
                print(f"✅ Found {len(game_logs)} game log entries")
            else:
                logger.warning("No game logs found in replay")
                print("⚠️  No game logs found - checking page content...")
                
                # Debug: check what we actually got
                if len(page_source) < 1000:
                    print(f"Page seems too short ({len(page_source)} chars)")
                    print("First 500 chars:", page_source[:500])
            
            # Try to extract player information
            player_elements = soup.find_all('span', class_='playername')
            for player_elem in player_elements:
                player_name = player_elem.get_text().strip()
                if player_name:
                    replay_data['players'].append(player_name)

            logger.info(f"Successfully scraped replay {replay_id}")
            return replay_data
            
        except Exception as e:
            logger.error(f"Error scraping replay {replay_id}: {e}")
            print(f"❌ Error scraping replay: {e}")
            return None
    
    def scrape_replay_logs_json(self, table_id: str) -> Dict:
        """
        Fetch raw replay gamelogs as JSON via the BGA archive API.

        A cheaper alternative to `scrape_replay()` for games whose parser
        does not need the static `gameui.completesetup` gamedatas (e.g.
        Tokaido). Skips loading the full replay HTML page; instead issues
        two XHRs from inside the authenticated browser session:
          1. /gamereview/gamereview/requestTableArchive.html?table=<id>
             (warms up the archive — required before logs.html will return)
          2. /archive/archive/logs.html?table=<id>&translated=true
             (returns {"data": {"logs": [<packets>]}})

        Args:
            table_id: BGA table ID

        Returns:
            dict with one of:
              {"success": True, "logs": [<packets>]}
              {"success": False, "error": "replay_limit_reached", "limit_reached": True}
              {"success": False, "error": "replay_deleted", "deleted": True}
              {"success": False, "error": "<reason>"}
        """
        if not self.driver:
            raise RuntimeError("Browser not started. Call start_browser() first.")

        try:
            # Get bgaConfig.requestToken from the current page. If we're not
            # on a BGA page yet, navigate to the lightweight /account page first.
            token = self.driver.execute_script(
                "return (typeof bgaConfig !== 'undefined' && bgaConfig.requestToken) ? bgaConfig.requestToken : '';"
            )
            if not token:
                self.driver.get("https://boardgamearena.com/account")
                time.sleep(1)
                token = self.driver.execute_script(
                    "return (typeof bgaConfig !== 'undefined' && bgaConfig.requestToken) ? bgaConfig.requestToken : '';"
                )
            if not token:
                return {"success": False, "error": "no_request_token"}

            warmup_url = f"/gamereview/gamereview/requestTableArchive.html?table={table_id}"
            logs_url = f"/archive/archive/logs.html?table={table_id}&translated=true"

            # Warm-up — body is irrelevant; the side-effect produces the archive.
            self.driver.execute_script(f"""
                var xhr = new XMLHttpRequest();
                xhr.open('GET', '{warmup_url}', false);
                xhr.setRequestHeader('X-Request-Token', '{token}');
                xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                try {{ xhr.send(); }} catch (e) {{}}
                return xhr.responseText;
            """)

            resp_text = self.driver.execute_script(f"""
                var xhr = new XMLHttpRequest();
                xhr.open('GET', '{logs_url}', false);
                xhr.setRequestHeader('X-Request-Token', '{token}');
                xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                xhr.send();
                return xhr.responseText;
            """)

            import json as _json
            try:
                j = _json.loads(resp_text or "{}")
            except _json.JSONDecodeError:
                return {"success": False, "error": "invalid_json"}

            if isinstance(j, dict) and j.get("error"):
                err = str(j["error"])
                if "reached a limit" in err:
                    return {"success": False, "error": "replay_limit_reached", "limit_reached": True}
                if any(s in err for s in ("Cannot find gamenotifs",
                                          "empty archive file",
                                          "doesn't exist")):
                    return {"success": False, "error": "replay_deleted", "deleted": True}
                if any(s in err for s in (
                    "Sorry, you need to be registered",
                    "Replaying games is currently disabled",
                )):
                    return {"success": False, "error": "no_replay_access"}
                return {"success": False, "error": err[:120]}

            try:
                logs = j["data"]["logs"]
            except (KeyError, TypeError):
                return {"success": False, "error": "missing_logs_field"}
            if not isinstance(logs, list):
                return {"success": False, "error": "logs_not_a_list"}
            return {"success": True, "logs": logs}

        except Exception as e:
            logger.warning(f"scrape_replay_logs_json error for table {table_id}: {e}")
            return {"success": False, "error": f"exception:{type(e).__name__}"}

    def initialize_session(self) -> bool:
        """
        Initialize authenticated session for direct HTTP requests
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.email or not self.password:
            logger.error("Email and password are required for session initialization")
            return False
        
        try:
            # Initialize session to get cookies
            if not self.session:
                print("🔐 Initializing session for direct requests...")
                self.session = BGASession(
                    email=self.email,
                    password=self.password,
                    chromedriver_path=self.chromedriver_path,
                    chrome_path=self.chrome_path,
                    headless=True  # Use headless for session-only initialization
                )
                
                if not self.session.login():
                    logger.error("Session initialization failed")
                    return False
            
            # Create requests session and copy cookies
            self.requests_session = requests.Session()
            
            # Get cookies from the browser session
            if self.session.driver:
                cookies = self.session.driver.get_cookies()
                for cookie in cookies:
                    self.requests_session.cookies.set(
                        cookie['name'], 
                        cookie['value'], 
                        domain=cookie.get('domain', '.boardgamearena.com')
                    )
                logger.info(f"Copied {len(cookies)} cookies to requests session")
            
            # Set appropriate headers
            self.requests_session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            })
            
            print("✅ Session initialized successfully!")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing session: {e}")
            return False

    def close_browser(self):
        """Close the browser and cleanup session"""
        if self.session:
            try:
                self.session.close_browser()
                print("Browser closed via session")
            except:
                pass
            finally:
                self.session = None
                self.driver = None
        elif self.driver:
            try:
                self.driver.quit()
                print("Browser closed")
            except:
                pass
            finally:
                self.driver = None
        
        # Close requests session
        if self.requests_session:
            try:
                self.requests_session.close()
                logger.info("Requests session closed")
            except:
                pass
            finally:
                self.requests_session = None

    def refresh_authentication(self, max_retries: int = 3, retry_delay: int = 2) -> bool:
        """
        Refresh authentication with retry logic when session expires
        
        Args:
            max_retries: Maximum number of retries for authentication
            retry_delay: Delay between retries in seconds
            
        Returns:
            bool: True if refresh successful, False otherwise
        """
        if not self.session:
            logger.warning("No session available for refresh, falling back to manual login")
            return self.login_to_bga()

        for attempt in range(max_retries):
            logger.info(f"Refreshing session authentication (attempt {attempt + 1}/{max_retries})...")
            print(f"🔄 Refreshing authentication (attempt {attempt + 1}/{max_retries})...")
            
            try:
                if self.session.refresh_authentication():
                    self.driver = self.session.get_driver()
                    print("✅ Authentication refreshed successfully!")
                    return True
                else:
                    logger.warning(f"Authentication refresh failed on attempt {attempt + 1}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
            except Exception as e:
                logger.error(f"Error refreshing authentication on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))

        print("❌ Authentication refresh failed after multiple retries")
        return False

    def _is_authentication_error(self, page_source: str) -> bool:
        """
        Check if the page source indicates an authentication error
        
        Returns True only for actual authentication failures, not for other errors like missing replays
        """
        page_content = page_source.lower()
        
        # Explicit authentication error indicators
        explicit_auth_errors = [
            'must be logged',
            'must be logged in',
            'please log in',
            'you must log in',
            'login required',
            'form_id="loginform"'
        ]
        
        for error_text in explicit_auth_errors:
            if error_text in page_content:
                return True
        
        # Check for fatal error only if it's authentication-related
        if 'fatalerror' in page_content or 'fatal error' in page_content:
            # Only treat as auth error if it mentions login/authentication
            auth_keywords = ['must be logged', 'log in', 'login', 'authenticate', 'session expired']
            if any(keyword in page_content for keyword in auth_keywords):
                return True
            # If it's a different kind of fatal error (like "Unable to find game archive"), not an auth error
            return False
        
        return False

    def _handle_authentication_error_with_retry(self, url: str, max_retries: int = 3, retry_delay: int = 2) -> bool:
        """
        Handle authentication errors with a retry mechanism
        
        Args:
            url: The URL that failed
            max_retries: Maximum number of retries
            retry_delay: Delay between retries in seconds
            
        Returns:
            bool: True if authentication was successful, False otherwise
        """
        for attempt in range(max_retries):
            logger.warning(f"Authentication error detected on attempt {attempt + 1}/{max_retries}, attempting re-authentication...")
            print(f"⚠️  Session expired! Attempting to re-authenticate (attempt {attempt + 1}/{max_retries})...")
            
            # Perform authentication refresh
            if self.refresh_authentication():
                # Retry the original URL (normalized to effective origin)
                print(f"Retrying replay page: {url}")
                nav_url = self._normalize_url_to_effective_origin(url)
                self.driver.get(nav_url)
                
                # Wait for page to load or replay content to render
                if '/archive/replay/' in url:
                    try:
                        replay_id = self._extract_replay_id(url)
                        self._wait_for_replay_content_to_load(replay_id or 'unknown')
                    except Exception:
                        time.sleep(self.speed_settings.get('page_load_delay', 2))
                else:
                    time.sleep(self.speed_settings.get('page_load_delay', 2))
                
                # Check if authentication is now successful
                page_source = self.driver.page_source
                if not self._is_authentication_error(page_source):
                    print("✅ Re-authentication successful!")
                    return True
                else:
                    logger.warning(f"Authentication still failed after successful refresh on attempt {attempt + 1}")
            
            # If we are here, re-authentication failed or the page still shows an error
            if attempt < max_retries - 1:
                print(f"Waiting {retry_delay}s before next retry...")
                time.sleep(retry_delay)
        
        return False
    
    def _is_deleted_replay(self, page_source: str) -> bool:
        """Check if the replay has been permanently lost/deleted."""
        page_lower = page_source.lower()
        return any(ind in page_lower for ind in [
            'replay for this game has been lost',
            'empty archive file',
            'unable to find game archive',
        ])

    def _check_replay_limit_reached(self, page_source: str) -> bool:
        """
        Check if the replay limit has been reached based on page content
        
        Args:
            page_source: HTML content of the page
            
        Returns:
            bool: True if replay limit reached, False otherwise
        """
        try:
            # Convert to lowercase for case-insensitive matching
            page_content = page_source.lower()
            
            # Check for the specific limit message patterns
            limit_indicators = [
                'you have reached a limit (replay)',
                'you have reached a limit',
                'reached a limit (replay)',
                'reached a limit',
                'replay limit',
                'limit reached',
                'daily replay limit'
            ]
            
            for indicator in limit_indicators:
                if indicator in page_content:
                    logger.info(f"Replay limit detected: found '{indicator}' in page content")
                    return True
            
            # Also check for the limit notification in structured content
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(page_source, 'html.parser')
                
                # Look for notification elements that might contain limit messages
                notification_selectors = [
                    'div.notification',
                    'div.alert',
                    'div.error',
                    'div.warning',
                    '.limit-message',
                    '[class*="limit"]',
                    '[class*="notification"]'
                ]
                
                for selector in notification_selectors:
                    elements = soup.select(selector)
                    for element in elements:
                        element_text = element.get_text().lower()
                        if any(indicator in element_text for indicator in limit_indicators):
                            logger.info(f"Replay limit detected in notification element: {element_text[:100]}")
                            return True
                
            except Exception as e:
                logger.debug(f"Error parsing HTML for limit detection: {e}")
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking replay limit: {e}")
            return False

    def _extract_replay_id(self, url: str) -> Optional[str]:
        """Extract replay ID from BGA replay URL (table parameter)"""
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(url)
            
            # Extract the table parameter from query string
            query_params = parse_qs(parsed.query)
            if 'table' in query_params:
                table_values = query_params['table']
                if table_values:
                    return table_values[0]  # Return the first table value
            
            return None
        except Exception as e:
            logger.error(f"Error extracting replay ID from {url}: {e}")
            return None

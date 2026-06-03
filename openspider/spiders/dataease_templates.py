import json
import os
from openspider.spiders.base import BaseSpider


class DataEaseTemplateSpider(BaseSpider):
    name = "dataease_templates"
    description = "Download all DataEase V2 templates"
    download_delay = 2.0
    timeout = 60
    concurrent_requests = 2

    async def run(self):
        base_url = "https://templates.dataease.cn"
        api_url = f"{base_url}/apis/api.store.halo.run/v1alpha1/applications?type=&deVersion=V2&page=0&size=200"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": base_url,
        }

        # Get template list
        page = await self.get(api_url, headers=headers)
        if not page:
            return

        # Parse JSON response
        try:
            # Try different ways to get the response body
            if hasattr(page, 'json'):
                data = page.json()
            elif hasattr(page, 'text'):
                data = json.loads(page.text)
            elif hasattr(page, 'body'):
                data = json.loads(page.body)
            else:
                return
            items = data.get("items", [])
            total = data.get("total", 0)
        except Exception as e:
            return

        for item in items:
            if self.should_stop:
                break

            app = item.get("application", {})
            spec = app.get("spec", {})
            metadata = app.get("metadata", {})

            app_name = metadata.get("name", "")
            display_name = spec.get("displayName", "")
            template_type = spec.get("templateType", "")
            price_mode = spec.get("priceConfig", {}).get("mode", "FREE")
            links = spec.get("links", [])

            # Get download URL
            download_url = ""
            for link in links:
                if link.get("name", "").find("下载") >= 0:
                    download_url = link.get("url", "")
                    break

            if not download_url and links:
                download_url = links[0].get("url", "")

            # Build full download URL
            full_download_url = ""
            if download_url:
                if download_url.startswith("http"):
                    full_download_url = download_url
                else:
                    full_download_url = f"{base_url}{download_url}"

            yield {
                "app_name": app_name,
                "display_name": display_name,
                "template_type": template_type,
                "price_mode": price_mode,
                "download_url": full_download_url,
                "download_link": download_url,
            }
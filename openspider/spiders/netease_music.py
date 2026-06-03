import json
from openspider.spiders.base import BaseSpider


class NeteaseMusicSpider(BaseSpider):
    name = "netease_music"
    description = "NetEase Cloud Music daily playlist spider"
    download_delay = 1.0
    timeout = 30
    max_retries = 3

    async def run(self):
        # Get daily recommended playlists
        api_url = "https://music.163.com/api/personalized/playlist?limit=10"
        headers = {
            "Referer": "https://music.163.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

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
            playlists = data.get("result", [])
        except Exception as e:
            return

        for playlist in playlists:
            if self.should_stop:
                break

            playlist_id = playlist.get("id")
            playlist_name = playlist.get("name", "")
            playlist_pic = playlist.get("picUrl", "")
            track_count = playlist.get("trackCount", 0)
            play_count = playlist.get("playCount", 0)

            # Get playlist details with tracks
            detail_url = f"https://music.163.com/api/playlist/detail?id={playlist_id}"
            detail_page = await self.get(detail_url, headers=headers)

            tracks = []
            if detail_page:
                try:
                    # Try different ways to get the response body
                    if hasattr(detail_page, 'json'):
                        detail_data = detail_page.json()
                    elif hasattr(detail_page, 'text'):
                        detail_data = json.loads(detail_page.text)
                    elif hasattr(detail_page, 'body'):
                        detail_data = json.loads(detail_page.body)
                    else:
                        continue
                    result = detail_data.get("result", {})
                    track_list = result.get("tracks", [])

                    for track in track_list[:10]:  # Get first 10 tracks
                        track_name = track.get("name", "")
                        artists = [a.get("name", "") for a in track.get("artists", [])]
                        album = track.get("album", {}).get("name", "")
                        duration = track.get("duration", 0) // 1000  # Convert to seconds

                        tracks.append({
                            "track_name": track_name,
                            "artists": ", ".join(artists),
                            "album": album,
                            "duration_seconds": duration,
                        })
                except Exception as e:
                    pass

            yield {
                "playlist_id": playlist_id,
                "playlist_name": playlist_name,
                "cover_url": playlist_pic,
                "track_count": track_count,
                "play_count": play_count,
                "tracks": tracks,
            }
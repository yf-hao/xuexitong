from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


class ForceV6ToV2Policy:
    """仅将课程主页跳转中的 v=6 转换为 v=2。"""

    def transform(self, source_url: str, redirect_url: str) -> str:
        parsed = urlparse(redirect_url)
        if parsed.path != "/mooc-ans/mycourse/teachercourse":
            return redirect_url

        query = parse_qs(parsed.query)
        if query.get("v", [None])[0] != "6":
            return redirect_url

        query["v"] = ["2"]
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
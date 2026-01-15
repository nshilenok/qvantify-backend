class DrawscapeFactorio:
    @staticmethod
    def normalize_tokens(value):
        try:
            return int(value or 0)
        except Exception:
            return 0

    @staticmethod
    def map_service(value, service_map, fallback="other"):
        if not value:
            return fallback
        return service_map.get(value, fallback)

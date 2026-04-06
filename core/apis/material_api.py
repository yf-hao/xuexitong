from typing import List

from models.data_types import Material


class MaterialAPI:
    """课程资料相关接口。"""

    def get_materials(self, course_id: str) -> List[Material]:
        """
        Fetch material/resource list for a specific course.
        Injects necessary parameters (clazzid, cpi, etc.) from session.
        """
        # Ensure params are loaded into session
        details = self.get_course_details(course_id)
        if not details:
            return []

        params = self.session_manager.course_params
        # At this point, params['clazzid'], params['cpi'], params['enc'] are available

        # Find the "资料" link
        material_url_path = None
        for link in details["nav_links"]:
            if "资料" in link["title"]:
                material_url_path = link["url"]
                break

        if not material_url_path:
            print(f"No material link found for course {course_id}.")
            return []

        print(f"Injecting params for material fetch - clazzid: {params.get('clazzid')}, cpi: {params.get('cpi')}")

        # In the next step, we will use these params to call the data fetching API
        # For now, return a status item showing the injection worked
        return [
            Material(
                id=params.get("clazzid", "0"),
                name=f"班级资料 (ID: {params.get('clazzid')})",
                type="folder"
            )
        ]

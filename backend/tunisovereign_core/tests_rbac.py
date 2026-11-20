from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from tunisovereign_core.models import CooperativeUnit, StakeholderUser

Role = StakeholderUser.Role

COOP_BODY = {"name": "RBAC Coop", "governorate": "Kasserine", "daily_quota_limit": 1000}


class RoleBasedAccessTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {
            role: StakeholderUser.objects.create_user(
                username=f"rbac_{role.lower()}", password="demo12345", role=role
            )
            for role in Role.values
        }
        cls.coop = CooperativeUnit.objects.create(
            name="Existing Coop", governorate="Gafsa", daily_quota_limit=500.0
        )

    def as_role(self, role):
        self.client.force_authenticate(user=self.users[role])

    # --- anonymous access ---------------------------------------------------
    def test_anonymous_cannot_read_cooperatives(self):
        self.assertEqual(self.client.get("/api/v1/cooperatives/").status_code, 401)

    # --- cooperatives: everybody reads, only the national admin writes -------
    def test_every_role_can_read_cooperatives(self):
        for role in Role.values:
            with self.subTest(role=role):
                self.as_role(role)
                self.assertEqual(self.client.get("/api/v1/cooperatives/").status_code, 200)

    def test_only_national_admin_can_create_a_cooperative(self):
        expected = {
            Role.COOP_MEMBER: 403,
            Role.REGIONAL_AUDITOR: 403,
            Role.AGENT_SERVICE: 403,
            Role.NATIONAL_ADMIN: 201,
        }
        for role, status_code in expected.items():
            with self.subTest(role=role):
                self.as_role(role)
                response = self.client.post("/api/v1/cooperatives/", COOP_BODY, format="json")
                self.assertEqual(response.status_code, status_code)

    def test_coop_member_cannot_delete_a_cooperative(self):
        self.as_role(Role.COOP_MEMBER)
        response = self.client.delete(f"/api/v1/cooperatives/{self.coop.id}/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(CooperativeUnit.objects.filter(id=self.coop.id).exists())

    # --- anomalies: auditors, agents and admins only ------------------------
    def test_coop_member_cannot_read_anomalies(self):
        self.as_role(Role.COOP_MEMBER)
        self.assertEqual(self.client.get("/api/v1/anomalies/").status_code, 403)

    def test_regional_auditor_can_read_anomalies(self):
        self.as_role(Role.REGIONAL_AUDITOR)
        self.assertEqual(self.client.get("/api/v1/anomalies/").status_code, 200)

    # --- telemetry writes are not open to field members ----------------------
    def test_coop_member_cannot_write_telemetry(self):
        self.as_role(Role.COOP_MEMBER)
        response = self.client.post("/api/v1/telemetry/", {}, format="json")
        self.assertEqual(response.status_code, 403)


class AuthEndpointTests(APITestCase):
    def test_register_ignores_a_requested_role(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "sneaky",
                "email": "sneaky@example.com",
                "password": "demo12345",
                "governorate": "Kasserine",
                "role": Role.NATIONAL_ADMIN,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(StakeholderUser.objects.get(username="sneaky").role, Role.COOP_MEMBER)

    def test_login_token_carries_the_role_claim(self):
        StakeholderUser.objects.create_user(
            username="claims_user", password="demo12345", role=Role.REGIONAL_AUDITOR
        )
        response = self.client.post(
            "/api/auth/login/",
            {"username": "claims_user", "password": "demo12345"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        token = AccessToken(response.data["access"])
        self.assertEqual(token["role"], Role.REGIONAL_AUDITOR)
        self.assertEqual(token["governorate"], "Kasserine")

    def test_refresh_endpoint_returns_a_new_access_token(self):
        StakeholderUser.objects.create_user(username="refresh_user", password="demo12345")
        login = self.client.post(
            "/api/auth/login/",
            {"username": "refresh_user", "password": "demo12345"},
            format="json",
        )
        response = self.client.post(
            "/api/auth/refresh/", {"refresh": login.data["refresh"]}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

"""
Built-in pure-Python Windows SSPI Negotiate and Kerberos/NTLM authentication.
Uses Windows native secur32.dll via ctypes with zero third-party dependencies.
Provides drop-in compatibility with requests.auth.AuthBase for Windows Single Sign-On (SSO)
and explicit domain credentials, including Kerberos ticket delegation to PI AF.
"""
import base64
import ctypes
from ctypes import wintypes
import logging
import socket
import urllib.parse
from typing import Optional, Tuple, Any
from requests.auth import AuthBase

logger = logging.getLogger(__name__)

# SSPI Constants from sspi.h / sspicon.h
SECPKG_CRED_OUTBOUND = 2
SEC_WINNT_AUTH_IDENTITY_UNICODE = 0x2
SECURITY_NATIVE_DREP = 0x10

SEC_E_OK = 0x00000000
SEC_I_CONTINUE_NEEDED = 0x00090312
SEC_I_COMPLETE_NEEDED = 0x00090313
SEC_I_COMPLETE_AND_CONTINUE = 0x00090314

SECBUFFER_EMPTY = 0
SECBUFFER_DATA = 1
SECBUFFER_TOKEN = 2
SECBUFFER_CHANNEL_BINDINGS = 14

ISC_REQ_DELEGATE = 0x00000001
ISC_REQ_MUTUAL_AUTH = 0x00000002
ISC_REQ_REPLAY_DETECT = 0x00000004
ISC_REQ_SEQUENCE_DETECT = 0x00000008
ISC_REQ_CONFIDENTIALITY = 0x00000010
ISC_REQ_CONNECTION = 0x00000800

try:
    secur32 = ctypes.windll.secur32
except Exception:
    secur32 = None


class SecHandle(ctypes.Structure):
    _fields_ = [
        ("dwLower", ctypes.c_void_p),
        ("dwUpper", ctypes.c_void_p)
    ]


class SecBuffer(ctypes.Structure):
    _fields_ = [
        ("cbBuffer", wintypes.ULONG),
        ("BufferType", wintypes.ULONG),
        ("pvBuffer", ctypes.c_void_p)
    ]


class SecBufferDesc(ctypes.Structure):
    _fields_ = [
        ("ulVersion", wintypes.ULONG),
        ("cBuffers", wintypes.ULONG),
        ("pBuffers", ctypes.POINTER(SecBuffer))
    ]


class SEC_WINNT_AUTH_IDENTITY_W(ctypes.Structure):
    _fields_ = [
        ("User", ctypes.c_wchar_p),
        ("UserLength", wintypes.ULONG),
        ("Domain", ctypes.c_wchar_p),
        ("DomainLength", wintypes.ULONG),
        ("Password", ctypes.c_wchar_p),
        ("PasswordLength", wintypes.ULONG),
        ("Flags", wintypes.ULONG)
    ]


class WindowsNegotiateAuth(AuthBase):
    """
    Built-in Windows SSPI Negotiate and Kerberos/NTLM authentication.
    Requires ZERO pip packages or compiled C extensions.
    Built directly on Windows secur32.dll.
    Supports:
      - Windows Single Sign-On (SSO) using current active Windows session (Username=None, Password=None)
      - Explicit domain credentials (DOMAIN\\username and Password)
      - Kerberos ticket delegation to downstream servers (e.g. PI AF Database)
    """
    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        domain: Optional[str] = None,
        service: str = "HTTP",
        host: Optional[str] = None,
        delegate: bool = True
    ):
        self.username = username
        self.password = password
        self.domain = domain
        self.service = service
        self.host = host
        self.delegate = delegate

    def _get_target_spn(self, request_url: str) -> str:
        if self.host:
            target_host = self.host
        else:
            parsed = urllib.parse.urlparse(request_url)
            target_host = parsed.hostname or "localhost"
        return f"{self.service}/{target_host}"

    def _acquire_credentials(self, package: str) -> Tuple[Optional[SecHandle], Optional[Any]]:
        if not secur32:
            return None, None

        cred_handle = SecHandle()
        pts_expiry = ctypes.c_int64()

        if self.username and self.password:
            domain_val = self.domain or "."
            user_val = self.username
            auth_id = SEC_WINNT_AUTH_IDENTITY_W(
                user_val, len(user_val),
                domain_val, len(domain_val),
                self.password, len(self.password),
                SEC_WINNT_AUTH_IDENTITY_UNICODE
            )
            p_auth = ctypes.byref(auth_id)
        else:
            # None = Single Sign-On with current logged-in Windows domain session!
            auth_id = None
            p_auth = None

        status = secur32.AcquireCredentialsHandleW(
            None,
            package,
            SECPKG_CRED_OUTBOUND,
            None,
            p_auth,
            None,
            None,
            ctypes.byref(cred_handle),
            ctypes.byref(pts_expiry)
        )
        if status != SEC_E_OK:
            logger.warning(f"AcquireCredentialsHandle failed for package {package}: 0x{status:08X}")
            return None, None
        return cred_handle, auth_id

    def _init_context(
        self,
        cred_handle: SecHandle,
        ctxt_handle: Optional[SecHandle],
        target_spn: str,
        input_token: Optional[bytes]
    ) -> Tuple[int, Optional[SecHandle], Optional[bytes]]:
        flags = (
            ISC_REQ_CONNECTION |
            ISC_REQ_MUTUAL_AUTH |
            ISC_REQ_REPLAY_DETECT |
            ISC_REQ_SEQUENCE_DETECT |
            ISC_REQ_CONFIDENTIALITY
        )
        if self.delegate:
            flags |= ISC_REQ_DELEGATE

        out_buf = ctypes.create_string_buffer(32768)
        out_sec_buf = SecBuffer(len(out_buf), SECBUFFER_TOKEN, ctypes.cast(out_buf, ctypes.c_void_p))
        out_desc = SecBufferDesc(0, 1, ctypes.pointer(out_sec_buf))

        new_ctxt = SecHandle() if ctxt_handle is None else ctxt_handle
        p_in_desc = None

        if input_token:
            in_buf = ctypes.create_string_buffer(input_token)
            in_sec_buf = SecBuffer(len(input_token), SECBUFFER_TOKEN, ctypes.cast(in_buf, ctypes.c_void_p))
            in_desc = SecBufferDesc(0, 1, ctypes.pointer(in_sec_buf))
            p_in_desc = ctypes.byref(in_desc)

        pts_expiry = ctypes.c_int64()
        ctx_attr = wintypes.ULONG()

        status = secur32.InitializeSecurityContextW(
            ctypes.byref(cred_handle),
            ctypes.byref(ctxt_handle) if ctxt_handle else None,
            target_spn,
            flags,
            0,
            SECURITY_NATIVE_DREP,
            p_in_desc,
            0,
            ctypes.byref(new_ctxt),
            ctypes.byref(out_desc),
            ctypes.byref(ctx_attr),
            ctypes.byref(pts_expiry)
        )

        out_token = None
        if out_sec_buf.cbBuffer > 0:
            out_token = out_buf.raw[:out_sec_buf.cbBuffer]

        return status, new_ctxt, out_token

    def _retry_using_negotiate(self, response, scheme: str, kwargs):
        if not secur32:
            return response

        if "Authorization" in response.request.headers:
            return response

        target_spn = self._get_target_spn(response.request.url)
        cred_handle, _auth_keepalive = self._acquire_credentials(scheme)
        if not cred_handle:
            return response

        try:
            status, ctxt_handle, token = self._init_context(cred_handle, None, target_spn, None)
            if not token:
                return response

            req = response.request.copy()
            req.headers["Authorization"] = f"{scheme} {base64.b64encode(token).decode('ascii')}"

            response.content
            response.raw.release_conn()

            args_nostream = dict(kwargs, stream=False)
            resp2 = response.connection.send(req, **args_nostream)

            # Step 2: If server responds with 401 challenge (e.g. NTLM 2-step challenge)
            if resp2.status_code == 401 and ctxt_handle:
                www_auth = resp2.headers.get("WWW-Authenticate", "")
                challenges = [
                    val[len(scheme):].strip()
                    for val in www_auth.split(",")
                    if val.strip().lower().startswith(scheme.lower())
                ]
                if challenges and challenges[0]:
                    server_token = base64.b64decode(challenges[0])
                    status2, ctxt_handle, token2 = self._init_context(
                        cred_handle, ctxt_handle, target_spn, server_token
                    )
                    if token2:
                        req2 = resp2.request.copy()
                        req2.headers["Authorization"] = f"{scheme} {base64.b64encode(token2).decode('ascii')}"
                        resp2.content
                        resp2.raw.release_conn()
                        resp3 = resp2.connection.send(req2, **kwargs)
                        resp3.history.append(response)
                        resp3.history.append(resp2)
                        return resp3

            resp2.history.append(response)
            return resp2

        finally:
            if secur32:
                try:
                    secur32.FreeCredentialsHandle(ctypes.byref(cred_handle))
                except Exception:
                    pass

    def _response_hook(self, r, **kwargs):
        if r.status_code == 401:
            www_auth = r.headers.get("WWW-Authenticate", "").lower()
            if "negotiate" in www_auth:
                return self._retry_using_negotiate(r, "Negotiate", kwargs)
            elif "ntlm" in www_auth:
                return self._retry_using_negotiate(r, "NTLM", kwargs)
        return r

    def __call__(self, r):
        r.headers["Connection"] = "Keep-Alive"
        r.register_hook("response", self._response_hook)
        return r

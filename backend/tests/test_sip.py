"""sip-engine 테스트 — SDP 파서/빌더, 메시지 직렬화, UA 흐름."""

from sim.sip import amrwb_offer, build_sdp, parse_sdp, sip_flow_event
from sim.sip.messages import SipMessage, build_invite, build_response, gen_call_id, gen_tag
from sim.sip.ua import CallerUA, UaState

# 실 로그에서 발췌한 caller SDP (AMR-WB octet-align)
REAL_SDP = (
    "v=0\r\no=- 12 1000 IN IP4 104.240.17.77\r\ns=QC VOIP\r\nc=IN IP4 104.240.17.77\r\n"
    "b=AS:41\r\nt=0 0\r\nm=audio 50020 RTP/AVP 98 97 101 99\r\n"
    "a=rtpmap:98 AMR-WB/16000/1\r\na=fmtp:98 octet-align=1;mode-change-capability=2;max-red=0\r\n"
    "a=rtpmap:97 AMR-WB/16000/1\r\na=rtpmap:101 AMR/8000/1\r\n"
    "a=rtpmap:99 telephone-event/16000\r\na=sendrecv\r\na=ptime:20\r\na=maxptime:240\r\n"
)


def test_parse_real_sdp():
    sdp = parse_sdp(REAL_SDP)
    assert sdp.ip == "104.240.17.77"
    audio = sdp.audio()
    assert audio is not None
    assert audio.port == 50020
    assert audio.direction == "sendrecv"
    assert audio.ptime == 20 and audio.maxptime == 240
    # 주 코덱은 AMR-WB
    primary = audio.primary_audio()
    assert primary.name == "AMR-WB" and primary.clock == 16000 and primary.channels == 1
    assert audio.is_octet_aligned(98) is True
    assert "AS:41" in sdp.bandwidth


def test_sdp_build_roundtrip():
    sdp = amrwb_offer("10.0.0.1", 30000, pt=98, mode_set=8)
    text = build_sdp(sdp)
    back = parse_sdp(text)
    assert back.audio().port == 30000
    assert back.audio().mode_set(98) == [8]
    assert back.audio().is_octet_aligned(98)


def test_mcptt_application_line():
    sdp_text = (
        "v=0\r\no=- 1 0 IN IP4 1.2.3.4\r\ns=-\r\nc=IN IP4 1.2.3.4\r\nt=0 0\r\n"
        "m=audio 30822 RTP/AVP 98\r\na=rtpmap:98 AMR-WB/16000/1\r\n"
        "a=fmtp:98 mode-set=8; octet-align=1\r\na=recvonly\r\n"
        "m=application 30826 UDP MCPTT\r\n"
    )
    sdp = parse_sdp(sdp_text)
    assert sdp.has_mcptt_app() is True
    assert sdp.audio().direction == "recvonly"


def test_invite_serialize_parse_roundtrip():
    cid = gen_call_id()
    inv = build_invite(
        call_id=cid, from_uri="<sip:+8210@ims>", to_uri="<tel:01012345678>",
        from_tag=gen_tag(), via_host="1.1.1.1", via_port=5060,
        contact="<sip:a@1.1.1.1>", sdp="v=0\r\n",
    )
    raw = inv.serialize()
    parsed = SipMessage.parse(raw)
    assert parsed.is_request and parsed.method == "INVITE"
    assert parsed.call_id == cid
    assert parsed.get("Content-Type") == "application/sdp"
    assert parsed.get("Content-Length") == str(len("v=0\r\n".encode()))


def test_response_reflects_via_and_callid():
    inv = build_invite(call_id="c@h", from_uri="<sip:a@x>", to_uri="<sip:b@y>",
                       from_tag="t1", via_host="2.2.2.2", via_port=5060,
                       contact="<sip:a@2.2.2.2>")
    resp = build_response(inv, 200, "OK", to_tag="t2")
    assert resp.status == 200
    assert resp.call_id == "c@h"
    assert "tag=t2" in resp.get("To")


def test_caller_ua_flow():
    ua = CallerUA(from_uri="<sip:a@x>", to_uri="<sip:b@y>", via_host="3.3.3.3")
    inv = ua.invite(sdp="v=0\r\n")
    assert ua.state == UaState.INVITING and inv.method == "INVITE"
    ringing = build_response(inv, 180, "Ringing", to_tag="zz")
    ua.on_response(ringing)
    assert ua.state == UaState.RINGING
    ok = build_response(inv, 200, "OK", to_tag="zz")
    ua.on_response(ok)
    assert ua.state == UaState.CONNECTED and ua.to_tag == "zz"
    bye = ua.bye()
    assert bye.method == "BYE" and ua.state == UaState.TERMINATING


def test_sip_flow_event_payload():
    inv = build_invite(call_id="c@h", from_uri="<sip:a@x>", to_uri="<sip:b@y>",
                       from_tag="t1", via_host="2.2.2.2", via_port=5060,
                       contact="<sip:a@2.2.2.2>")
    ev = sip_flow_event(inv, session_id="s1", direction="SIM->SUT", peer="VCSM")
    assert ev.channel == "SIP" and ev.label == "INVITE"
    assert ev.call_id == "c@h"
    assert "raw" in ev.payload and "INVITE" in ev.payload["raw"]

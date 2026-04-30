import { NextResponse } from 'next/server';
import { AccessToken, type AccessTokenOptions, type VideoGrant } from 'livekit-server-sdk';
import { RoomConfiguration } from '@livekit/protocol';

type ConnectionDetails = {
  serverUrl: string;
  roomName: string;
  participantName: string;
  participantToken: string;
};

// NOTE: you are expected to define the following environment variables in `.env`:
const API_KEY = process.env.LIVEKIT_API_KEY;
const API_SECRET = process.env.LIVEKIT_API_SECRET;
const LIVEKIT_URL = process.env.LIVEKIT_URL;

// don't cache the results
export const revalidate = 0;

// Same whitelist as the API agent-runner uses for room names (api/routes_test.py).
// 1–64 chars, alphanumerics plus _ and -.
const ROOM_NAME_RE = /^[A-Za-z0-9_-]{1,64}$/;

export async function POST(req: Request) {
  // Auth is enforced by middleware.ts (ADMIN_PASSWORD + session cookie).
  // If ADMIN_PASSWORD is unset the middleware passes all requests through (local dev).
  try {
    if (LIVEKIT_URL === undefined) {
      throw new Error('LIVEKIT_URL is not defined');
    }
    if (API_KEY === undefined) {
      throw new Error('LIVEKIT_API_KEY is not defined');
    }
    if (API_SECRET === undefined) {
      throw new Error('LIVEKIT_API_SECRET is not defined');
    }

    // Parse JSON body. Surface parse errors as 400 instead of silently
    // treating the request as `{}` — this makes client bugs debuggable.
    let body: Record<string, unknown> = {};
    try {
      const raw = await req.text();
      if (raw.trim().length > 0) {
        body = JSON.parse(raw);
      }
    } catch {
      return new NextResponse('Invalid JSON body', { status: 400 });
    }
    // fromJson throws if given undefined/null — guard with an empty object.
    // RoomConfiguration.fromJson expects protobuf JsonValue, which is too
    // narrow for the unstructured body we accept; cast through unknown.
    const roomConfigInput = (body?.room_config ?? {}) as Parameters<
      typeof RoomConfiguration.fromJson
    >[0];
    const roomConfig = RoomConfiguration.fromJson(roomConfigInput, {
      ignoreUnknownFields: true,
    });

    // If a profile is specified, set it as room metadata so the agent can
    // dynamically load the correct YAML profile at runtime.
    const profile = body?.profile;
    if (profile && typeof profile === 'string') {
      roomConfig.metadata = JSON.stringify({ profile });
    }

    // Generate participant token
    const participantName = 'user';
    const participantIdentity = `voice_assistant_user_${Math.floor(Math.random() * 10_000)}`;
    // Allow `body.room` override (POST JSON, not a query param) for connect-mode
    // local testing — the agent is already in that room and the browser tab opened
    // by Try needs to join the same one. Validate against a whitelist so callers
    // can't smuggle arbitrary strings into the LiveKit grant.
    let roomName: string;
    if (body?.room && typeof body.room === 'string') {
      if (!ROOM_NAME_RE.test(body.room)) {
        return new NextResponse('Invalid room name', { status: 400 });
      }
      roomName = body.room;
    } else {
      roomName = `voice_assistant_room_${Math.floor(Math.random() * 10_000)}`;
    }

    const participantToken = await createParticipantToken(
      { identity: participantIdentity, name: participantName },
      roomName,
      roomConfig
    );

    // Return connection details
    const data: ConnectionDetails = {
      serverUrl: LIVEKIT_URL,
      roomName,
      participantName,
      participantToken,
    };
    const headers = new Headers({
      'Cache-Control': 'no-store',
    });
    return NextResponse.json(data, { headers });
  } catch (error) {
    if (error instanceof Error) {
      console.error(error);
      return new NextResponse(error.message, { status: 500 });
    }
  }
}

function createParticipantToken(
  userInfo: AccessTokenOptions,
  roomName: string,
  roomConfig: RoomConfiguration
): Promise<string> {
  const at = new AccessToken(API_KEY, API_SECRET, {
    ...userInfo,
    ttl: '15m',
  });
  const grant: VideoGrant = {
    room: roomName,
    roomJoin: true,
    canPublish: true,
    canPublishData: true,
    canSubscribe: true,
  };
  at.addGrant(grant);

  if (roomConfig) {
    at.roomConfig = roomConfig;
  }

  return at.toJwt();
}

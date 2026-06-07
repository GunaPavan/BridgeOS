/**
 * Cognito helpers — thin wrappers around amazon-cognito-identity-js so the
 * auth pages stay small.
 */

import {
  CognitoUser,
  CognitoUserAttribute,
  CognitoUserPool,
  AuthenticationDetails,
  CognitoUserSession,
} from "amazon-cognito-identity-js";

const POOL_ID =
  process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID || "us-east-1_fanxkrBlF";
const CLIENT_ID =
  process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID || "2uodkgu469969oe4fukh73d7b8";

let _pool: CognitoUserPool | null = null;

function pool(): CognitoUserPool {
  if (!_pool) {
    _pool = new CognitoUserPool({ UserPoolId: POOL_ID, ClientId: CLIENT_ID });
  }
  return _pool;
}

export type SignupRole = "donor" | "patient";

// ---------------------------------------------------------------------------
// Sign up
// ---------------------------------------------------------------------------

export interface SignUpParams {
  email: string;
  password: string;
  role: SignupRole;
  name?: string;
  phone?: string;
}

export function signUp(params: SignUpParams): Promise<{ userSub: string }> {
  return new Promise((resolve, reject) => {
    const attrs: CognitoUserAttribute[] = [
      new CognitoUserAttribute({ Name: "email", Value: params.email }),
      new CognitoUserAttribute({
        Name: "custom:signup_role",
        Value: params.role,
      }),
    ];
    if (params.name) {
      attrs.push(new CognitoUserAttribute({ Name: "name", Value: params.name }));
    }
    if (params.phone) {
      attrs.push(
        new CognitoUserAttribute({
          Name: "phone_number",
          Value: params.phone,
        }),
      );
    }
    pool().signUp(
      params.email,
      params.password,
      attrs,
      [],
      (err, result) => {
        if (err) return reject(err);
        resolve({ userSub: result?.userSub ?? "" });
      },
    );
  });
}

// ---------------------------------------------------------------------------
// Confirm sign up (email verification code)
// ---------------------------------------------------------------------------

export function confirmSignUp(email: string, code: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const user = new CognitoUser({ Username: email, Pool: pool() });
    user.confirmRegistration(code, true, (err) => {
      if (err) return reject(err);
      resolve();
    });
  });
}

export function resendConfirmationCode(email: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const user = new CognitoUser({ Username: email, Pool: pool() });
    user.resendConfirmationCode((err) => {
      if (err) return reject(err);
      resolve();
    });
  });
}

// ---------------------------------------------------------------------------
// Sign in (handles "force change password" flow for admin-created users)
// ---------------------------------------------------------------------------

export interface SignInResult {
  tokens: {
    idToken: string;
    accessToken: string;
    refreshToken: string;
  };
  email: string;
  groups: string[];
}

export function signIn(
  email: string,
  password: string,
  opts?: { newPassword?: string },
): Promise<SignInResult> {
  return new Promise((resolve, reject) => {
    const user = new CognitoUser({ Username: email, Pool: pool() });
    const auth = new AuthenticationDetails({
      Username: email,
      Password: password,
    });

    user.authenticateUser(auth, {
      onSuccess: (session) => resolve(_toSignInResult(session, email)),
      onFailure: (err) => reject(err),
      newPasswordRequired: (userAttrs, _required) => {
        // Admin-created users get this on first login
        if (!opts?.newPassword) {
          const err = new Error(
            "FORCE_CHANGE_PASSWORD: please choose a new password",
          );
          (err as Error & { code?: string }).code = "FORCE_CHANGE_PASSWORD";
          return reject(err);
        }
        // Don't try to re-send email attribute — Cognito rejects it
        delete (userAttrs as Record<string, unknown>).email_verified;
        delete (userAttrs as Record<string, unknown>).email;
        user.completeNewPasswordChallenge(opts.newPassword, userAttrs, {
          onSuccess: (session) => resolve(_toSignInResult(session, email)),
          onFailure: (err2) => reject(err2),
        });
      },
    });
  });
}

function _toSignInResult(session: CognitoUserSession, email: string): SignInResult {
  const idToken = session.getIdToken();
  const payload = idToken.payload as Record<string, unknown>;
  const groups = (payload["cognito:groups"] as string[] | undefined) ?? [];
  return {
    tokens: {
      idToken: idToken.getJwtToken(),
      accessToken: session.getAccessToken().getJwtToken(),
      refreshToken: session.getRefreshToken().getToken(),
    },
    email,
    groups,
  };
}

// ---------------------------------------------------------------------------
// Token / session helpers
// ---------------------------------------------------------------------------

export function getCurrentUser(): CognitoUser | null {
  return pool().getCurrentUser();
}

export function signOut(): void {
  pool().getCurrentUser()?.signOut();
}

export function getIdTokenForRequest(): Promise<string | null> {
  return new Promise((resolve) => {
    const u = pool().getCurrentUser();
    if (!u) return resolve(null);
    u.getSession((err: Error | null, session: CognitoUserSession | null) => {
      if (err || !session?.isValid()) return resolve(null);
      resolve(session.getIdToken().getJwtToken());
    });
  });
}

export function decodeTokenClaims(token: string): {
  email?: string;
  sub?: string;
  groups?: string[];
  linkedId?: string;
} {
  try {
    const part = token.split(".")[1];
    const payload = JSON.parse(
      Buffer.from(part, "base64").toString("utf-8"),
    ) as Record<string, unknown>;
    return {
      email: payload.email as string | undefined,
      sub: payload.sub as string | undefined,
      groups: payload["cognito:groups"] as string[] | undefined,
      linkedId: payload["custom:linked_id"] as string | undefined,
    };
  } catch {
    return {};
  }
}

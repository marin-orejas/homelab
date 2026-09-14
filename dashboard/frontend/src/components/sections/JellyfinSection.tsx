import type { LibraryInfo, Maybe, SessionsInfo, StreamSession } from "../../api/types";
import { isError } from "../../api/types";
import { count } from "../../lib/format";
import { Band, Bar, Chip, Note, Stat } from "../primitives";

export function JellyfinSection({
  sessions,
  library,
}: {
  sessions: Maybe<SessionsInfo>;
  library: Maybe<LibraryInfo>;
}) {
  const libraryFailed = isError(library);
  const sessionsFailed = isError(sessions);
  const down = libraryFailed || sessionsFailed;

  const playing = !sessionsFailed && sessions.active_count > 0;

  return (
    <Band
      name="Jellyfin"
      note={libraryFailed ? "not answering" : (library.server.version ?? undefined)}
      severity={down ? "critical" : "good"}
      wide
    >
      {down ? (
        <div className="alert">
          <strong>Jellyfin is not answering.</strong>{" "}
          {isError(library) ? library.error : isError(sessions) ? sessions.error : null} The
          host figures above come from the kernel and are unaffected.
        </div>
      ) : null}

      <div className="cells cells--head">
        <Stat
          label="Films"
          value={libraryFailed ? "—" : count(library.counts.movies)}
          sub={libraryFailed ? undefined : "on toshiba2tb"}
        />
        <Stat
          label="Series"
          value={libraryFailed ? "—" : count(library.counts.series)}
          sub={libraryFailed ? undefined : `${count(library.counts.episodes)} episodes`}
        />
        <Stat
          label="Playing now"
          value={sessionsFailed ? "—" : count(sessions.active_count)}
          sub={
            sessionsFailed
              ? undefined
              : `${sessions.transcoding_count} transcoding, ${sessions.direct_play_count} direct`
          }
        />
        <Stat
          label="Server"
          value={
            <Chip
              severity={
                libraryFailed
                  ? "critical"
                  : library.server.has_pending_restart
                    ? "warning"
                    : playing
                      ? "good"
                      : "idle"
              }
            >
              {libraryFailed
                ? "Offline"
                : library.server.has_pending_restart
                  ? "Restart pending"
                  : playing
                    ? "Streaming"
                    : "Idle"}
            </Chip>
          }
          sub={
            libraryFailed
              ? undefined
              : library.server.has_update_available
                ? "an update is available"
                : "up to date"
          }
        />
      </div>

      {!sessionsFailed && sessions.sessions.length > 0 ? (
        <div className="streams">
          {sessions.sessions.map((session) => (
            <Stream key={session.session_id} session={session} />
          ))}
        </div>
      ) : !down ? (
        <div className="empty">
          Nothing is playing. A row appears here for each stream, with who is
          watching, on what, how far in, and why it is being transcoded.
        </div>
      ) : null}

      {!sessionsFailed && sessions.idle_client_count > 0 ? (
        <Note>
          {sessions.idle_client_count} client
          {sessions.idle_client_count === 1 ? " is" : "s are"} connected without
          playing anything.
        </Note>
      ) : null}
    </Band>
  );
}

function Stream({ session }: { session: StreamSession }) {
  const { item, play_state: state, transcoding } = session;
  const who = [session.user, session.device, session.client].filter(Boolean).join(", ");

  return (
    <article className="stream">
      <div className="stream__top">
        <span className="stream__title">{item?.title ?? "Unknown title"}</span>
        <Chip severity={transcoding ? "warning" : "good"}>
          {transcoding
            ? `Transcoding${
                transcoding.hardware_acceleration
                  ? ` on ${transcoding.hardware_acceleration.toUpperCase()}`
                  : " in software"
              }`
            : "Direct play"}
        </Chip>
      </div>

      {who ? <p className="stream__who">{who}</p> : null}

      <Bar percent={state.progress_percent} height="sm" />
      <p className="stream__meta">
        {state.progress_percent !== null ? `${Math.round(state.progress_percent)} % in` : "position unknown"}
        {state.is_paused ? ", paused" : ", playing"}
        {state.play_method ? `, ${state.play_method}` : ""}
      </p>

      {transcoding && transcoding.reasons.length > 0 ? (
        <div className="reasons">
          {transcoding.reasons.map((reason) => (
            <span className="reason" key={reason}>
              {reason.replace(/([a-z])([A-Z])/g, "$1 $2").toLowerCase()}
            </span>
          ))}
        </div>
      ) : null}
    </article>
  );
}

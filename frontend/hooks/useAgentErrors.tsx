import { ReactNode, useEffect } from 'react';
import { toast as sonnerToast } from 'sonner';
import { useAgent, useSessionContext } from '@livekit/components-react';
import { WarningIcon } from '@phosphor-icons/react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

interface ToastProps {
  title: ReactNode;
  description: ReactNode;
}

function toastAlert(toast: ToastProps) {
  const { title, description } = toast;

  return sonnerToast.custom(
    (id) => (
      <Alert onClick={() => sonnerToast.dismiss(id)} className="bg-accent w-full md:w-[364px]">
        <WarningIcon weight="bold" />
        <AlertTitle>{title}</AlertTitle>
        {description && <AlertDescription>{description}</AlertDescription>}
      </Alert>
    ),
    { duration: 10_000 }
  );
}

export function useAgentErrors() {
  const agent = useAgent();
  const { isConnected, end } = useSessionContext();

  useEffect(() => {
    // Diagnostic: capture agent.state transitions + attribute visibility.
    // Kept post-fix so we can confirm lk.agent.state reaches "listening" on
    // connect-mode sessions. Safe to remove once connect-mode stability is
    // confirmed across multiple profiles.
    const agentParticipant = agent.internal?.agentParticipant;
    console.log('[agent]', agent.state, {
      agentStateAttr: agentParticipant?.attributes?.['lk.agent.state'] ?? null,
      agentIdentity: agentParticipant?.identity ?? null,
      failureReasons: agent.failureReasons,
    });

    if (isConnected && agent.state === 'failed') {
      const reasons = agent.failureReasons;
      console.error('[agent] → failed, calling session.end()', { reasons });

      toastAlert({
        title: 'Session ended',
        description: (
          <>
            {reasons.length > 1 && (
              <ul className="list-inside list-disc">
                {reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            )}
            {reasons.length === 1 && <p className="w-full">{reasons[0]}</p>}
            <p className="w-full">
              <a
                target="_blank"
                rel="noopener noreferrer"
                href="https://docs.livekit.io/agents/start/voice-ai/"
                className="whitespace-nowrap underline"
              >
                See quickstart guide
              </a>
              .
            </p>
          </>
        ),
      });

      end();
    }
  }, [agent, isConnected, end]);
}

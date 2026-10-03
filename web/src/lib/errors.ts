import { ApiError } from "../api/client";

/** The sentence to show for any error: the server's own message when it sent one. */
export function messageOf(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof TypeError)
    return "Memoir could not reach the server. Check the connection.";
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

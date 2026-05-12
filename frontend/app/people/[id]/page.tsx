"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import {
  addPersonAlias,
  approvePersonFace,
  createPersonQuickMemory,
  deleteDirectoryEntry,
  fetchPeopleDirectory,
  fetchPersonActivity,
  fetchPersonDetail,
  fetchPersonSuggestedFaces,
  linkPersonToCompreface,
  mergePeopleEntries,
  removePersonAlias,
  renameDirectoryEntry,
  splitPersonEntry,
  updatePersonContact,
  resolveApiUrl,
} from "../../lib/memoirApi";
import { DirectoryEntry, EventFaceEntry, PersonActivity, PersonDetail } from "../../types";

export default function PersonDetailsPage() {
  const params = useParams<{ id: string }>();
  const personId = Number(params?.id || 0);

  const [person, setPerson] = useState<PersonDetail | null>(null);
  const [activity, setActivity] = useState<PersonActivity | null>(null);
  const [peopleDirectory, setPeopleDirectory] = useState<DirectoryEntry[]>([]);
  const [suggestedFaces, setSuggestedFaces] = useState<EventFaceEntry[]>([]);
  const [status, setStatus] = useState<string>("");
  const [isBusy, setIsBusy] = useState(false);

  const [newAlias, setNewAlias] = useState("");
  const [renameValue, setRenameValue] = useState("");
  const [mergeTargetId, setMergeTargetId] = useState("");
  const [splitNames, setSplitNames] = useState("");
  const [splitKeepAlias, setSplitKeepAlias] = useState(true);

  const [quickMemoryText, setQuickMemoryText] = useState("");
  const [fullMemoryText, setFullMemoryText] = useState("");
  const [fullMemoryDateText, setFullMemoryDateText] = useState("");

  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [address, setAddress] = useState("");
  const [notes, setNotes] = useState("");
  const [birthdayText, setBirthdayText] = useState("");
  const [comprefaceSubjectName, setComprefaceSubjectName] = useState("");

  const mergeTargets = useMemo(
    () => peopleDirectory.filter((entry) => entry.id !== personId),
    [peopleDirectory, personId],
  );

  async function loadAll() {
    if (!personId || Number.isNaN(personId)) {
      return;
    }

    const [personData, activityData, peopleData, faceData] = await Promise.all([
      fetchPersonDetail(personId),
      fetchPersonActivity(personId),
      fetchPeopleDirectory(),
      fetchPersonSuggestedFaces(personId),
    ]);

    setPerson(personData);
    setActivity(activityData);
    setPeopleDirectory(peopleData);
    setSuggestedFaces(faceData);

    setRenameValue(personData.name);
    setPhone(personData.contact.phone ?? "");
    setEmail(personData.contact.email ?? "");
    setAddress(personData.contact.address ?? "");
    setNotes(personData.contact.notes ?? "");
    setBirthdayText(personData.contact.birthday_text ?? "");
    setComprefaceSubjectName(personData.compreface_subject_id ?? personData.name);
  }

  useEffect(() => {
    loadAll().catch((error) => {
      setStatus(error instanceof Error ? error.message : "Failed to load person details");
    });
  }, [personId]);

  async function runMutation(action: () => Promise<void>, success: string) {
    setIsBusy(true);
    try {
      await action();
      await loadAll();
      setStatus(success);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Action failed");
    } finally {
      setIsBusy(false);
    }
  }

  if (!personId || Number.isNaN(personId)) {
    return <main><p>Invalid person id.</p></main>;
  }

  return (
    <main>
      <div className="personDetailsHero">
        <a href="/" className="ghost">Back to timeline</a>
        <h1>{person?.name ?? "Loading person..."}</h1>
        <p className="meta">Manage profile, memories, events, photos, and face approvals.</p>
        {status ? <p className="status">{status}</p> : null}
      </div>

      <section className="panel personDetailsGrid">
        <article className="personColumn">
          <h2>Contact Details</h2>
          <label>
            Phone
            <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Phone number" />
          </label>
          <label>
            Email
            <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" />
          </label>
          <label>
            Address
            <input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="Address" />
          </label>
          <label>
            Birthday
            <input value={birthdayText} onChange={(e) => setBirthdayText(e.target.value)} placeholder="e.g. 1958-04-22" />
          </label>
          <label>
            Notes
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes about this person" rows={4} />
          </label>
          <button
            className="primary"
            disabled={isBusy}
            onClick={() => runMutation(async () => {
              await updatePersonContact(personId, {
                phone,
                email,
                address,
                notes,
                birthday_text: birthdayText,
              });
            }, "Contact details saved.")}
          >
            Save Contact Details
          </button>
        </article>

        <article className="personColumn">
          <h2>Identity Actions</h2>
          <label>
            Name
            <input value={renameValue} onChange={(e) => setRenameValue(e.target.value)} />
          </label>
          <button
            className="secondary"
            disabled={isBusy || !renameValue.trim()}
            onClick={() => runMutation(async () => {
              await renameDirectoryEntry("people", personId, renameValue.trim());
            }, "Name updated.")}
          >
            Rename
          </button>

          <div className="personInlineRow">
            <input
              value={newAlias}
              onChange={(e) => setNewAlias(e.target.value)}
              placeholder="Add alias"
            />
            <button
              className="secondary"
              disabled={isBusy || !newAlias.trim()}
              onClick={() => runMutation(async () => {
                await addPersonAlias(personId, newAlias.trim());
                setNewAlias("");
              }, "Alias added.")}
            >
              Add Alias
            </button>
          </div>

          <div className="aliasList">
            {(person?.aliases ?? []).map((alias) => (
              <span key={alias} className="aliasChip">
                {alias}
                <button
                  className="aliasRemove"
                  disabled={isBusy}
                  onClick={() => runMutation(async () => {
                    await removePersonAlias(personId, alias);
                  }, "Alias removed.")}
                >
                  ×
                </button>
              </span>
            ))}
          </div>

          <label>
            CompreFace subject
            <input
              value={comprefaceSubjectName}
              onChange={(e) => setComprefaceSubjectName(e.target.value)}
              placeholder="Subject name"
            />
          </label>
          <button
            className="secondary"
            disabled={isBusy || !comprefaceSubjectName.trim()}
            onClick={() => runMutation(async () => {
              await linkPersonToCompreface(personId, comprefaceSubjectName.trim());
            }, "CompreFace link updated.")}
          >
            Link CompreFace Subject
          </button>

          <label>
            Merge into
            <select value={mergeTargetId} onChange={(e) => setMergeTargetId(e.target.value)}>
              <option value="">Select person</option>
              {mergeTargets.map((entry) => (
                <option key={entry.id} value={entry.id}>{entry.name}</option>
              ))}
            </select>
          </label>
          <button
            className="secondary"
            disabled={isBusy || !mergeTargetId}
            onClick={() => runMutation(async () => {
              await mergePeopleEntries(personId, Number(mergeTargetId));
              window.location.href = `/people/${mergeTargetId}`;
            }, "People merged.")}
          >
            Merge Person
          </button>

          <label>
            Split into (comma-separated names)
            <input value={splitNames} onChange={(e) => setSplitNames(e.target.value)} />
          </label>
          <label className="personCheckboxRow">
            <input type="checkbox" checked={splitKeepAlias} onChange={(e) => setSplitKeepAlias(e.target.checked)} />
            Keep current name as alias on new people
          </label>
          <button
            className="secondary"
            disabled={isBusy || !splitNames.trim()}
            onClick={() => runMutation(async () => {
              const names = splitNames.split(",").map((n) => n.trim()).filter(Boolean);
              await splitPersonEntry(personId, names, splitKeepAlias);
              window.location.href = "/";
            }, "Person split.")}
          >
            Split Person
          </button>

          <button
            className="ghost"
            disabled={isBusy}
            onClick={() => runMutation(async () => {
              await deleteDirectoryEntry("people", personId);
              window.location.href = "/";
            }, "Person deleted.")}
          >
            Delete Person
          </button>
        </article>
      </section>

      <section className="panel personSection">
        <h2>Memories</h2>
        <div className="personInlineRow">
          <input
            value={quickMemoryText}
            onChange={(e) => setQuickMemoryText(e.target.value)}
            placeholder="Quick memory note"
          />
          <button
            className="secondary"
            disabled={isBusy || !quickMemoryText.trim()}
            onClick={() => runMutation(async () => {
              await createPersonQuickMemory(personId, { text: quickMemoryText.trim() });
              setQuickMemoryText("");
            }, "Quick memory added.")}
          >
            Add Quick Memory
          </button>
        </div>

        <div className="personFullMemoryForm">
          <textarea
            value={fullMemoryText}
            onChange={(e) => setFullMemoryText(e.target.value)}
            placeholder="Full memory about this person"
            rows={4}
          />
          <input
            value={fullMemoryDateText}
            onChange={(e) => setFullMemoryDateText(e.target.value)}
            placeholder="Optional date text"
          />
          <button
            className="secondary"
            disabled={isBusy || !fullMemoryText.trim()}
            onClick={() => runMutation(async () => {
              await createPersonQuickMemory(personId, {
                text: fullMemoryText.trim(),
                estimated_date_text: fullMemoryDateText.trim() || null,
              });
              setFullMemoryText("");
              setFullMemoryDateText("");
            }, "Memory saved.")}
          >
            Save Full Memory
          </button>
        </div>

        <div className="personSimpleList">
          {(activity?.memories ?? []).map((memory) => (
            <div key={memory.id} className="personListCard">
              <strong>{memory.event_description || "Untitled memory"}</strong>
              <p>{memory.transcript}</p>
            </div>
          ))}
          {activity && activity.memories.length === 0 ? <p className="meta">No memories linked yet.</p> : null}
        </div>
      </section>

      <section className="panel personSection">
        <h2>Events</h2>
        <div className="personSimpleList">
          {(activity?.events ?? []).map((event) => (
            <div key={event.id} className="personListCard">
              <strong>{event.title}</strong>
              <p>{event.event_date_text || "No event date"}</p>
              <p>{event.description || ""}</p>
            </div>
          ))}
          {activity && activity.events.length === 0 ? <p className="meta">No events linked yet.</p> : null}
        </div>
      </section>

      <section className="panel personSection">
        <h2>Pictures</h2>
        <div className="personAssetGrid">
          {(activity?.assets ?? []).map((asset) => (
            <figure key={asset.id} className="personAssetCard">
              <img src={resolveApiUrl(`${asset.download_url}?download=false`)} alt={asset.title ?? "Linked photo"} />
              <figcaption>{asset.title || asset.original_filename || `Photo #${asset.id}`}</figcaption>
            </figure>
          ))}
          {activity && activity.assets.length === 0 ? <p className="meta">No photos linked yet.</p> : null}
        </div>
      </section>

      <section className="panel personSection">
        <h2>Face Approvals</h2>
        <div className="personSimpleList">
          {suggestedFaces.map((face) => (
            <div key={face.id} className="personListCard">
              <p>
                Suggested subject: <strong>{face.compreface_subject || "Unknown"}</strong>
                {typeof face.compreface_similarity === "number" ? ` (${Math.round(face.compreface_similarity * 100)}%)` : ""}
              </p>
              <img
                className="personFacePreview"
                src={resolveApiUrl(`${face.asset_download_url}?download=false`)}
                alt="Suggested face"
              />
              <button
                className="secondary"
                disabled={isBusy}
                onClick={() => runMutation(async () => {
                  await approvePersonFace(personId, face.id);
                }, "Face approved and synced to CompreFace.")}
              >
                Approve Face
              </button>
            </div>
          ))}
          {suggestedFaces.length === 0 ? <p className="meta">No pending suggested faces.</p> : null}
        </div>
      </section>
    </main>
  );
}

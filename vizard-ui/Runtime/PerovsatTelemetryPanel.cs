using System;
using System.Collections.Generic;
using System.Globalization;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;
using Storage = VizProtobufferMessage.VizMessage.Types.GenericStorage;

public sealed class PerovsatTelemetryPanel : MonoBehaviour
{
    private static readonly Color Background = Hex("101925");
    private static readonly Color Surface = Hex("192637");
    private static readonly Color Track = Hex("2A3A4D");
    private static readonly Color Ink = Hex("EDF3FA");
    private static readonly Color Muted = Hex("A2B3C8");
    private static readonly Color Teal = Hex("50D9D0");
    private static readonly Color Gold = Hex("F3C267");
    private static readonly Color Blue = Hex("7BAAF7");
    private static readonly Color Red = Hex("FF858B");
    private readonly Dictionary<string, Reading> readings = new Dictionary<string, Reading>();
    private readonly Dictionary<string, Storage> latest = new Dictionary<string, Storage>();
    private readonly List<TMP_FontAsset> ownedFonts = new List<TMP_FontAsset>();
    private TMP_FontAsset regular;
    private TMP_FontAsset semibold;
    private TMP_Text freshness;
    private RectTransform panel;
    private int spacecraftIndex;
    private string spacecraftName;
    private double lastSimulationTime = double.NaN;
    private float lastAdvance;

    private sealed class Reading
    {
        public TMP_Text Value;
        public TMP_Text Detail;
        public RectTransform Fill;
        public Color Accent;
        public string Unit;
        public string Format;
    }

    public static void Attach(GameObject host, int index, string name)
    {
        if (DataManager.UseVR || host.GetComponent<PerovsatTelemetryPanel>() != null)
            return;
        var message = MessageList.FirstMessage;
        if (message == null || index < 0 || index >= message.Spacecraft.Count)
            return;
        bool hasBattery = false;
        bool hasFaces = false;
        foreach (var storage in message.Spacecraft[index].StorageDevices)
        {
            hasBattery |= storage.Label == "Battery SOC";
            hasFaces |= storage.Label == "Face +X illumination";
        }
        if (!hasBattery || !hasFaces)
            return;
        var view = host.AddComponent<PerovsatTelemetryPanel>();
        view.spacecraftIndex = index;
        view.spacecraftName = name;
    }

    private void Start()
    {
        regular = LoadFont("Barlow-Regular");
        semibold = LoadFont("Barlow-SemiBold");
        panel = GetComponent<RectTransform>();
        var close = GetComponentInChildren<ClosePanelButton>(true);
        foreach (Transform child in transform)
            child.gameObject.SetActive(false);
        var canvas = GetComponentInParent<Canvas>();
        float availableHeight = canvas != null ? canvas.GetComponent<RectTransform>().rect.height - 32 : 908;
        float panelHeight = Mathf.Clamp(availableHeight, 360, 908);
        panel.sizeDelta = new Vector2(408, panelHeight);
        var baseImage = GetComponent<Image>();
        if (baseImage != null)
            baseImage.color = Background;
        var root = Box("PEROVSAT telemetry", panel, 0, 0, 408, panelHeight, Background);
        var heading = Text(root, spacecraftName.ToUpperInvariant(), 20, 14, 320, 26, 21, Ink, true);
        heading.richText = false;
        Text(root, "SPACECRAFT TELEMETRY", 20, 42, 310, 18, 11, Muted);
        var handle = Box("Drag header", root, 0, 0, 360, 66, new Color(0, 0, 0, 0));
        handle.gameObject.AddComponent<PerovsatTelemetryDrag>().Target = panel;
        if (close != null)
        {
            close.gameObject.SetActive(true);
            close.transform.SetAsLastSibling();
            var closeRect = close.GetComponent<RectTransform>();
            Place(closeRect, 370, 16, 22, 22);
        }

        var viewport = Box("Viewport", root, 12, 70, 384, panelHeight - 104, Background);
        viewport.gameObject.AddComponent<RectMask2D>();
        var content = Box("Content", viewport, 0, 0, 384, 804, Background);
        var scroll = viewport.gameObject.AddComponent<ScrollRect>();
        scroll.viewport = viewport;
        scroll.content = content;
        scroll.horizontal = false;
        scroll.vertical = true;
        scroll.movementType = ScrollRect.MovementType.Clamped;
        scroll.scrollSensitivity = 22;

        Section(content, "POWER SYSTEM", 0);
        Card(content, "Battery SOC", "BATTERY", "%", "0.0", 0, 26, 188, 92, Teal);
        Card(content, "Stored energy", "STORED ENERGY", "Wh", "0.00", 196, 26, 188, 92, Blue);
        Card(content, "Solar generation", "SOLAR", "W", "0.00", 0, 126, 122, 80, Gold);
        Card(content, "Electrical load", "LOAD", "W", "0.00", 131, 126, 122, 80, Blue);
        Card(content, "Power balance", "BALANCE", "W", "0.00", 262, 126, 122, 80, Teal);
        Section(content, "SUNLIGHT / BODY FACES", 224);
        Line(content, "Sun visible (eclipse)", "Sun visible", "%", "0.0", 250, Gold);
        string[] faces = { "+X", "-X", "+Y", "-Y", "+Z", "-Z" };
        for (int index = 0; index < faces.Length; index++)
        {
            Card(content, "Face " + faces[index] + " illumination", faces[index] + " FACE",
                "%", "0.0", index % 2 * 196, 298 + index / 2 * 82, 188, 74, Gold);
        }
        Section(content, "RUN TIMING", 558);
        float timingTop = 584;
        TimingLine(content, "Simulation elapsed", "Elapsed", "s", "0.0", ref timingTop, Blue);
        TimingLine(content, "Simulation cadence (configured)", "Configured cadence", "Hz", "0.0", ref timingTop, Blue);
        TimingLine(content, "Measured simulation updates", "Measured updates", "Hz", "0.0", ref timingTop, Teal);
        TimingLine(content, "Achieved simulation speed", "Achieved speed", "x", "0.00", ref timingTop, Teal);
        TimingLine(content, "Pacing lag (previous tick)", "Previous-tick lag", "s", "0.000", ref timingTop, Gold);
        content.sizeDelta = new Vector2(384, timingTop);
        panelHeight = Mathf.Min(panelHeight, timingTop + 104);
        panel.sizeDelta = new Vector2(408, panelHeight);
        root.sizeDelta = panel.sizeDelta;
        viewport.sizeDelta = new Vector2(384, panelHeight - 104);
        freshness = Text(root, "WAITING FOR TELEMETRY", 20, panelHeight - 24, 370, 16, 10, Muted);
        Update();
    }

    private void Update()
    {
        if (freshness == null)
            return;
        var message = MessageList.CurrentMessage;
        if (message == null || spacecraftIndex < 0 || spacecraftIndex >= message.Spacecraft.Count)
        {
            freshness.text = "TELEMETRY UNAVAILABLE";
            return;
        }
        latest.Clear();
        foreach (var storage in message.Spacecraft[spacecraftIndex].StorageDevices)
            latest[storage.Label] = storage;
        foreach (var pair in readings)
        {
            Storage storage;
            var reading = pair.Value;
            if (!latest.TryGetValue(pair.Key, out storage))
            {
                reading.Value.text = "—";
                reading.Detail.text = "Not enabled";
                SetFill(reading, 0, Muted);
                continue;
            }
            var detail = Status(storage.Units);
            bool pending = detail.IndexOf("awaiting", StringComparison.OrdinalIgnoreCase) >= 0
                || detail.IndexOf("warming", StringComparison.OrdinalIgnoreCase) >= 0
                || detail.IndexOf("unavailable", StringComparison.OrdinalIgnoreCase) >= 0;
            bool valid = !double.IsNaN(storage.CurrentValue) && !double.IsInfinity(storage.CurrentValue)
                && storage.CurrentValue >= 0 && !pending;
            reading.Value.text = valid
                ? storage.CurrentValue.ToString(reading.Format, CultureInfo.InvariantCulture) + " <size=65%>" + reading.Unit + "</size>"
                : "—";
            reading.Detail.text = detail;
            Color accent = reading.Accent;
            if (pair.Key == "Battery SOC" && valid)
                accent = storage.CurrentValue <= 20 ? Red : storage.CurrentValue < 40 ? Gold : Teal;
            if (detail.IndexOf("LATE", StringComparison.OrdinalIgnoreCase) >= 0
                || detail.IndexOf("deficit", StringComparison.OrdinalIgnoreCase) >= 0)
                accent = Gold;
            reading.Value.color = valid ? Ink : Muted;
            reading.Detail.color = accent;
            SetFill(reading, valid && storage.MaxValue > 0 ? (float)(storage.CurrentValue / storage.MaxValue) : 0, accent);
        }
        Storage elapsed;
        if (latest.TryGetValue("Simulation elapsed", out elapsed) && elapsed.CurrentValue != lastSimulationTime)
        {
            lastSimulationTime = elapsed.CurrentValue;
            lastAdvance = Time.unscaledTime;
        }
        bool paused = MessageList.PlaybackPaused || Time.unscaledTime - lastAdvance > 3;
        freshness.text = paused ? "PAUSED / NO NEW FRAME  ·  values held" : "UPDATING  ·  Direct sunlight model";
        freshness.color = paused ? Gold : Teal;
    }

    public static string Status(string units)
    {
        if (string.IsNullOrEmpty(units))
            return "";
        int separator = units.IndexOf('|');
        return separator < 0 ? "" : units.Substring(separator + 1).Trim();
    }

    private static void SetFill(Reading reading, float fraction, Color color)
    {
        if (reading.Fill == null)
            return;
        reading.Fill.anchorMax = new Vector2(Mathf.Clamp01(fraction), 1);
        reading.Fill.GetComponent<Image>().color = color;
    }

    private void Card(RectTransform parent, string key, string title, string unit, string format,
        float left, float top, float width, float height, Color accent)
    {
        var card = Box(title, parent, left, top, width, height, Surface);
        Text(card, title, 12, 8, width - 24, 16, 10, Muted, true);
        var value = Text(card, "—", 12, 23, width - 24, 26, 25, Ink, true);
        var detail = Text(card, "Awaiting data", 12, height - 22, width - 24, 13, 10, accent);
        var track = Box("Track", card, 12, height - 7, width - 24, 2, Track);
        var fill = Box("Fill", track, 0, 0, 0, 2, accent);
        fill.anchorMin = Vector2.zero;
        fill.anchorMax = Vector2.one;
        fill.offsetMin = Vector2.zero;
        fill.offsetMax = Vector2.zero;
        readings[key] = new Reading { Value = value, Detail = detail, Fill = fill,
            Accent = accent, Unit = unit, Format = format };
    }

    private void Line(RectTransform parent, string key, string title, string unit,
        string format, float top, Color accent)
    {
        var row = Box(title, parent, 0, top, 384, 40, Surface);
        Text(row, title, 12, 5, 200, 18, 12, Muted);
        var value = Text(row, "—", 215, 6, 156, 26, 19, Ink, true);
        value.alignment = TextAlignmentOptions.TopRight;
        var detail = Text(row, "", 12, 24, 205, 13, 9, accent);
        readings[key] = new Reading { Value = value, Detail = detail,
            Accent = accent, Unit = unit, Format = format };
    }

    private void TimingLine(RectTransform parent, string key, string title, string unit,
        string format, ref float top, Color accent)
    {
        foreach (var storage in MessageList.FirstMessage.Spacecraft[spacecraftIndex].StorageDevices)
        {
            if (storage.Label != key)
                continue;
            Line(parent, key, title, unit, format, top, accent);
            top += 44;
            return;
        }
    }

    private void Section(RectTransform parent, string title, float top)
    {
        Text(parent, title, 4, top, 376, 20, 11, Muted, true);
    }

    private TMP_Text Text(RectTransform parent, string value, float left, float top,
        float width, float height, float size, Color color, bool bold = false)
    {
        var node = new GameObject(value, typeof(RectTransform), typeof(TextMeshProUGUI));
        node.transform.SetParent(parent, false);
        Place(node.GetComponent<RectTransform>(), left, top, width, height);
        var text = node.GetComponent<TextMeshProUGUI>();
        text.font = bold ? semibold : regular;
        text.fontSize = size;
        text.color = color;
        text.text = value;
        text.raycastTarget = false;
        text.enableWordWrapping = false;
        text.overflowMode = TextOverflowModes.Ellipsis;
        return text;
    }

    private TMP_FontAsset LoadFont(string name)
    {
        var font = Resources.Load<Font>("PerovsatTelemetry/" + name);
        if (font == null)
            throw new InvalidOperationException("Missing PEROVSAT font: " + name);
        var asset = TMP_FontAsset.CreateFontAsset(font);
        ownedFonts.Add(asset);
        return asset;
    }

    private static RectTransform Box(string name, RectTransform parent, float left,
        float top, float width, float height, Color color)
    {
        var node = new GameObject(name, typeof(RectTransform), typeof(Image));
        node.transform.SetParent(parent, false);
        var rectangle = node.GetComponent<RectTransform>();
        Place(rectangle, left, top, width, height);
        node.GetComponent<Image>().color = color;
        return rectangle;
    }

    private static void Place(RectTransform rectangle, float left, float top, float width, float height)
    {
        rectangle.anchorMin = new Vector2(0, 1);
        rectangle.anchorMax = new Vector2(0, 1);
        rectangle.pivot = new Vector2(0, 1);
        rectangle.anchoredPosition = new Vector2(left, -top);
        rectangle.sizeDelta = new Vector2(width, height);
    }

    private static Color Hex(string value)
    {
        Color color;
        ColorUtility.TryParseHtmlString("#" + value, out color);
        return color;
    }

    private void OnDestroy()
    {
        foreach (var font in ownedFonts)
            Destroy(font);
    }
}

public sealed class PerovsatTelemetryDrag : MonoBehaviour, IDragHandler
{
    public RectTransform Target;

    public void OnDrag(PointerEventData eventData)
    {
        var canvas = Target.GetComponentInParent<Canvas>();
        Target.anchoredPosition += eventData.delta / (canvas != null ? canvas.scaleFactor : 1);
    }
}

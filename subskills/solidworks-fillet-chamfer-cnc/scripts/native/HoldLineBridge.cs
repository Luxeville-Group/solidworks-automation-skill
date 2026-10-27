using System;
using System.Collections;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

namespace CadStudio.SolidWorks
{
    /// <summary>
    /// Create hold-line face fillets using strongly typed official SolidWorks PIA setters.
    /// </summary>
    internal static class HoldLineBridge
    {
        private const double ToleranceM = 1e-5;
        private const string FeatureName = "Advanced_Hold_Line_Fillet";

        /// <summary>
        /// Console entry point; argument 1 is the active document title in the Python session.
        /// </summary>
        [STAThread]
        private static int Main(string[] args)
        {
            Console.OutputEncoding = Encoding.UTF8;
            var result = new Dictionary<string, object>();
            try
            {
                if (args.Length != 1 || String.IsNullOrWhiteSpace(args[0]))
                {
                    throw new ArgumentException("Etkin SolidWorks belge başlığı gerekir / Active SolidWorks document title required");
                }

                CreateHoldLineFillet(args[0], result);
                result["status"] = "verified";
                Console.WriteLine(ToJson(result));
                return 0;
            }
            catch (Exception exception)
            {
                result["status"] = "blocked";
                result["errorType"] = exception.GetType().FullName;
                result["error"] = exception.Message;
                Console.WriteLine(ToJson(result));
                return 2;
            }
        }

        /// <summary>
        /// Attach to SolidWorks, find face sets and hold lines by geometric signatures, and create the feature.
        /// </summary>
        private static void CreateHoldLineFillet(string expectedTitle, IDictionary<string, object> result)
        {
            var application = (ISldWorks)Marshal.GetActiveObject("SldWorks.Application");
            IModelDoc2 model = application.IActiveDoc2 as IModelDoc2;
            if (model == null)
            {
                throw new InvalidOperationException("SolidWorks etkin belgesi yok / No active SolidWorks document");
            }

            string actualTitle = model.GetTitle();
            result["expectedTitle"] = expectedTitle;
            result["actualTitle"] = actualTitle;
            if (!String.Equals(actualTitle, expectedTitle, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException(
                    String.Format("Köprü yanlış belgeye bağlandı / Wrong document: expected {0}, actual {1}", expectedTitle, actualTitle));
            }

            var part = model as IPartDoc;
            if (part == null)
            {
                throw new InvalidOperationException("Etkin belge parça değil / Active document is not a part");
            }

            object[] bodies = AsObjectArray(part.GetBodies2((int)swBodyType_e.swSolidBody, false));
            if (bodies.Length != 1)
            {
                throw new InvalidOperationException(String.Format("Test parçası tek katı olmalıdır / Test part requires one body; actual {0}", bodies.Length));
            }

            var body = (IBody2)bodies[0];
            IFace2 innerTop = FindUniqueFace(body, delegate(double[] box)
            {
                return Near(box[1], -0.025) && Near(box[4], 0.021)
                    && Near(box[2], 0.016) && Near(box[5], 0.016);
            });
            IFace2 outerTop = FindUniqueFace(body, delegate(double[] box)
            {
                return Near(box[1], 0.021) && Near(box[4], 0.025)
                    && Near(box[2], 0.016) && Near(box[5], 0.016);
            });
            IFace2 side = FindUniqueFace(body, delegate(double[] box)
            {
                return Near(box[1], 0.025) && Near(box[4], 0.025);
            });
            IEdge holdLine = FindUniqueEdge(body, delegate(double[] first, double[] second)
            {
                return Near(Math.Abs(first[0] - second[0]), 0.060)
                    && Near(first[1], 0.021) && Near(second[1], 0.021)
                    && Near(first[2], 0.016) && Near(second[2], 0.016);
            });

            var attempts = new List<object>();
            Feature feature = null;
            foreach (IFace2 top in new[] { innerTop, outerTop })
            {
                foreach (string encoding in new[] { "object-array", "edge-array" })
                {
                    var attempt = new Dictionary<string, object>();
                    attempt["top"] = Object.ReferenceEquals(top, innerTop) ? "inner" : "outer";
                    attempt["encoding"] = encoding;
                    try
                    {
                        model.ClearSelection2(true);
                        if (!((IEntity)top).Select2(false, 2)
                            || !((IEntity)side).Select2(true, 4)
                            || !((IEntity)holdLine).Select2(true, 8))
                        {
                            throw new InvalidOperationException("Yüz grubu veya tutma çizgisi seçilemedi / Face-set or hold-line selection failed");
                        }

                        var data = model.FeatureManager.CreateDefinition(
                            (int)swFeatureNameID_e.swFmFillet) as ISimpleFilletFeatureData2;
                        if (data == null || !data.Initialize((int)swSimpleFilletType_e.swFaceFillet))
                        {
                            throw new InvalidOperationException("ISimpleFilletFeatureData2 başlatılamadı / initialization failed");
                        }

                        data.ConicTypeForCrossSectionProfile =
                            (int)swFeatureFilletProfileType_e.swFeatureFilletCircular;
                        data.SetFaces(1, new object[] { top });
                        data.SetFaces(2, new object[] { side });
                        data.HoldLines = encoding == "edge-array"
                            ? (object)new IEdge[] { holdLine }
                            : (object)new object[] { holdLine };

                        int count = data.GetHoldLineCount();
                        attempt["holdLineCountBeforeCreate"] = count;
                        attempt["faceSet1Count"] = data.GetFaceCount(1);
                        attempt["faceSet2Count"] = data.GetFaceCount(2);
                        if (count != 1)
                        {
                            throw new InvalidOperationException(
                                String.Format("HoldLines setter okunan adet / readback count: {0}", count));
                        }

                        feature = model.FeatureManager.CreateFeature(data);
                        if (feature == null)
                        {
                            throw new InvalidOperationException("CreateFeature null döndürdü / returned null");
                        }
                        feature.Name = FeatureName;
                        if (!model.ForceRebuild3(false))
                        {
                            throw new InvalidOperationException("Tutma çizgisi radyüsü rebuild başarısız / Hold-line fillet rebuild failed");
                        }

                        var persistedData = feature.GetDefinition() as ISimpleFilletFeatureData2;
                        if (persistedData == null)
                        {
                            throw new InvalidOperationException("Tutma çizgisi FeatureData okunamıyor / Cannot read hold-line FeatureData");
                        }
                        bool selectionAccess = persistedData.AccessSelections(model, null);
                        int persistedCount = persistedData.GetHoldLineCount();
                        if (selectionAccess)
                        {
                            persistedData.ReleaseSelectionAccess();
                        }
                        attempt["persistedHoldLineCount"] = persistedCount;
                        attempt["featureType"] = feature.GetTypeName2();
                        attempt["created"] = persistedCount == 1;
                        attempts.Add(attempt);
                        if (persistedCount != 1)
                        {
                            throw new InvalidOperationException(
                                String.Format("Kalıcı tutma çizgisi adedi / Persisted hold-line count: {0}", persistedCount));
                        }

                        result["backend"] = "csharp-pia";
                        result["featureName"] = FeatureName;
                        result["holdLineCount"] = persistedCount;
                        result["attempts"] = attempts;
                        return;
                    }
                    catch (Exception exception)
                    {
                        attempt["created"] = false;
                        attempt["errorType"] = exception.GetType().FullName;
                        attempt["error"] = exception.Message;
                        attempts.Add(attempt);
                    }
                }
            }

            result["backend"] = "csharp-pia";
            result["attempts"] = attempts;
            throw new InvalidOperationException("C# PIA HoldLines okunabilir radyüs oluşturamadı / C# PIA HoldLines produced no readable hold-line fillet");
        }

        /// <summary>Find a unique face by bounding-box semantics.</summary>
        private static IFace2 FindUniqueFace(IBody2 body, Predicate<double[]> predicate)
        {
            var matches = new List<IFace2>();
            foreach (object item in AsObjectArray(body.GetFaces()))
            {
                var face = (IFace2)item;
                if (predicate(AsDoubleArray(face.GetBox())))
                {
                    matches.Add(face);
                }
            }
            if (matches.Count != 1)
            {
                throw new InvalidOperationException(String.Format("Hedef yüz eşleşme adedi / Target face match count: {0}", matches.Count));
            }
            return matches[0];
        }

        /// <summary>Find a unique hold-line edge by endpoint semantics.</summary>
        private static IEdge FindUniqueEdge(
            IBody2 body,
            Func<double[], double[], bool> predicate)
        {
            var matches = new List<IEdge>();
            foreach (object item in AsObjectArray(body.GetEdges()))
            {
                var edge = (IEdge)item;
                var start = edge.GetStartVertex() as IVertex;
                var end = edge.GetEndVertex() as IVertex;
                if (start != null && end != null
                    && predicate(AsDoubleArray(start.GetPoint()), AsDoubleArray(end.GetPoint())))
                {
                    matches.Add(edge);
                }
            }
            if (matches.Count != 1)
            {
                throw new InvalidOperationException(String.Format("Hedef tutma çizgisi adedi / Target hold-line match count: {0}", matches.Count));
            }
            return matches[0];
        }

        /// <summary>Convert COM SAFEARRAY to an object array.</summary>
        private static object[] AsObjectArray(object value)
        {
            var array = value as Array;
            if (array == null)
            {
                return new object[0];
            }
            var result = new object[array.Length];
            int index = 0;
            foreach (object item in array)
            {
                result[index++] = item;
            }
            return result;
        }

        /// <summary>Convert COM SAFEARRAY to a double array.</summary>
        private static double[] AsDoubleArray(object value)
        {
            var array = value as Array;
            if (array == null)
            {
                return new double[0];
            }
            var result = new double[array.Length];
            int index = 0;
            foreach (object item in array)
            {
                result[index++] = Convert.ToDouble(item);
            }
            return result;
        }

        /// <summary>Compare coordinates with tolerances in meters.</summary>
        private static bool Near(double left, double right)
        {
            return Math.Abs(left - right) <= ToleranceM;
        }

        /// <summary>Generate minimal JSON without third-party dependencies.</summary>
        private static string ToJson(object value)
        {
            if (value == null)
            {
                return "null";
            }
            var text = value as string;
            if (text != null)
            {
                return "\"" + text.Replace("\\", "\\\\").Replace("\"", "\\\"")
                    .Replace("\r", "\\r").Replace("\n", "\\n") + "\"";
            }
            if (value is bool)
            {
                return (bool)value ? "true" : "false";
            }
            var dictionary = value as IDictionary;
            if (dictionary != null)
            {
                var items = new List<string>();
                foreach (DictionaryEntry entry in dictionary)
                {
                    items.Add(ToJson(Convert.ToString(entry.Key)) + ":" + ToJson(entry.Value));
                }
                return "{" + String.Join(",", items.ToArray()) + "}";
            }
            var enumerable = value as IEnumerable;
            if (enumerable != null)
            {
                var items = new List<string>();
                foreach (object item in enumerable)
                {
                    items.Add(ToJson(item));
                }
                return "[" + String.Join(",", items.ToArray()) + "]";
            }
            return Convert.ToString(value, System.Globalization.CultureInfo.InvariantCulture);
        }
    }
}
